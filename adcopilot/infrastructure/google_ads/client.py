"""Google Ads client adapter — wraps google-ads-python behind the port protocol."""

from typing import Any

import structlog

from adcopilot.application.ports.google_ads import CustomerInfo
from adcopilot.config import Settings
from adcopilot.domain.exceptions import (
    GoogleAdsAuthError,
    GoogleAdsTokenNotApproved,
    GoogleAdsUnavailable,
)

logger = structlog.get_logger(__name__)

# Substrings (lower-cased) that indicate an OAuth/authentication failure.
# These appear in Google Ads API error messages and in google-auth library
# errors when the refresh token is invalid or has been revoked.
_AUTH_ERROR_SIGNATURES = (
    "unauthenticated",
    "invalid credentials",
    "invalid_grant",
    "token has been expired or revoked",
    "oauth_token_invalid",
    "authenticationerror",
    "access_denied",
)

# Substrings (lower-cased) that indicate the developer token is not approved
# for production use (i.e. it is a test token or pending approval).
_TEST_TOKEN_SIGNATURES = (
    "developer token",
    "developertoken",
    "developer_token",
    "not approved",
    "test account",
)


def is_test_token_error(exc: Exception) -> bool:
    """Return True if *exc* indicates the developer token is in test/unapproved state."""
    error_str = str(exc).lower()
    return any(sig in error_str for sig in _TEST_TOKEN_SIGNATURES)


def is_google_auth_error(exc: Exception) -> bool:
    """Return True if *exc* represents an OAuth/authentication failure.

    Detects both transient credential errors (expired access token that the
    library could not refresh) and permanent errors (revoked refresh token,
    invalid client_id/secret).
    """
    error_str = str(exc).lower()
    return any(sig in error_str for sig in _AUTH_ERROR_SIGNATURES)


# Substrings indicating Google Ads throttled the request (quota exhausted /
# rate limited). Such requests are rejected before processing, so retrying with
# back-off is safe.
_RATE_LIMIT_SIGNATURES = (
    "quota",
    "resource exhausted",
    "resource_exhausted",
    "rate exceeded",
    "rate_exceeded",
    "too many requests",
)


def is_rate_limit_error(exc: Exception) -> bool:
    """Return True if *exc* indicates a Google Ads quota / rate-limit error."""
    error_str = str(exc).lower()
    return any(sig in error_str for sig in _RATE_LIMIT_SIGNATURES)


class GoogleAdsClientAdapter:
    """Thin wrapper around the google-ads library.

    Builds a new client per call using the per-user refresh_token.
    Never reuses a global client across users.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _build_client(self, refresh_token: str) -> Any:
        """Build a google-ads GoogleAdsClient for the given refresh_token."""
        try:
            import google.ads.googleads.client as gads

            config = {
                "developer_token": self._settings.GOOGLE_ADS_DEVELOPER_TOKEN or "",
                "client_id": self._settings.GOOGLE_ADS_CLIENT_ID or "",
                "client_secret": self._settings.GOOGLE_ADS_CLIENT_SECRET or "",
                "refresh_token": refresh_token,
                "use_proto_plus": True,
            }
            return gads.GoogleAdsClient.load_from_dict(config)
        except Exception as exc:
            if is_google_auth_error(exc):
                raise GoogleAdsAuthError(f"OAuth credentials rejected: {exc}") from exc
            raise GoogleAdsUnavailable(f"Failed to build Google Ads client: {exc}") from exc

    async def list_accessible_customers(self, refresh_token: str) -> list[str]:
        """Returns list of accessible customer resource names.

        The google-ads library uses synchronous gRPC under the hood.
        We run it in a thread so it does not block the async event loop.
        """
        import asyncio

        def _blocking() -> list[str]:
            try:
                client = self._build_client(refresh_token)
                customer_service = client.get_service("CustomerService")
                response = customer_service.list_accessible_customers()
                return list(response.resource_names)
            except GoogleAdsAuthError:
                raise
            except Exception as exc:
                if is_google_auth_error(exc):
                    raise GoogleAdsAuthError(str(exc)) from exc
                if is_test_token_error(exc):
                    raise GoogleAdsTokenNotApproved(
                        "Developer token is in test mode or not yet approved for production access. "
                        "Apply for Standard Access at Google Ads → Admin → API Center."
                    ) from exc
                raise GoogleAdsUnavailable(str(exc)) from exc

        return await asyncio.wait_for(
            asyncio.to_thread(_blocking),
            timeout=30,
        )

    async def get_customer_info(self, refresh_token: str, customer_id: str) -> CustomerInfo:
        """Returns basic customer info for the given customer_id.

        The google-ads library uses synchronous gRPC under the hood.
        We run it in a thread so it does not block the async event loop.
        """
        import asyncio

        def _blocking() -> CustomerInfo:
            try:
                client = self._build_client(refresh_token)
                ga_service = client.get_service("GoogleAdsService")
                query = """
                    SELECT
                        customer.descriptive_name,
                        customer.currency_code,
                        customer.time_zone,
                        customer.manager
                    FROM customer
                    LIMIT 1
                """
                response = ga_service.search(customer_id=customer_id.replace("-", ""), query=query)
                for row in response:
                    return CustomerInfo(
                        descriptive_name=row.customer.descriptive_name,
                        currency=row.customer.currency_code,
                        timezone=row.customer.time_zone,
                        is_manager=row.customer.manager,
                    )
                raise GoogleAdsUnavailable(f"No customer data returned for {customer_id}")
            except (GoogleAdsAuthError, GoogleAdsUnavailable):
                raise
            except Exception as exc:
                if is_google_auth_error(exc):
                    raise GoogleAdsAuthError(str(exc)) from exc
                raise GoogleAdsUnavailable(str(exc)) from exc

        return await asyncio.wait_for(
            asyncio.to_thread(_blocking),
            timeout=20,
        )
