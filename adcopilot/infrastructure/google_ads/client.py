"""Google Ads client adapter — wraps google-ads-python behind the port protocol."""

from typing import Any

import structlog

from adcopilot.application.ports.google_ads import CustomerInfo
from adcopilot.config import Settings
from adcopilot.domain.exceptions import GoogleAdsAuthError, GoogleAdsUnavailable

logger = structlog.get_logger(__name__)


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
            raise GoogleAdsUnavailable(f"Failed to build Google Ads client: {exc}") from exc

    async def list_accessible_customers(self, refresh_token: str) -> list[str]:
        """Returns list of accessible customer resource names."""
        try:
            client = self._build_client(refresh_token)
            customer_service = client.get_service("CustomerService")
            response = customer_service.list_accessible_customers()
            result: list[str] = list(response.resource_names)
            return result
        except GoogleAdsAuthError:
            raise
        except Exception as exc:
            error_str = str(exc).lower()
            if "unauthenticated" in error_str or "invalid credentials" in error_str:
                raise GoogleAdsAuthError(str(exc)) from exc
            raise GoogleAdsUnavailable(str(exc)) from exc

    async def get_customer_info(self, refresh_token: str, customer_id: str) -> CustomerInfo:
        """Returns basic customer info for the given customer_id."""
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
            response = ga_service.search(
                customer_id=customer_id.replace("-", ""), query=query
            )
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
            error_str = str(exc).lower()
            if "unauthenticated" in error_str or "invalid credentials" in error_str:
                raise GoogleAdsAuthError(str(exc)) from exc
            raise GoogleAdsUnavailable(str(exc)) from exc
