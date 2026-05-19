class AdCopilotError(Exception):
    """Base exception for all adcopilot errors."""


class UserNotFoundError(AdCopilotError):
    pass


class AccountNotFoundError(AdCopilotError):
    pass


class GoogleAdsAuthError(AdCopilotError):
    pass


class GoogleAdsRateLimited(AdCopilotError):
    pass


class GoogleAdsUnavailable(AdCopilotError):
    pass


class GoogleAdsTokenNotApproved(AdCopilotError):
    """Raised when the developer token is in test mode or pending approval.

    Production access requires applying at Google Ads → Admin → API Center.
    """


class LLMError(AdCopilotError):
    """Raised when the LLM backend fails (rate limit, timeout, API error)."""


class PageAnalyzerError(AdCopilotError):
    """Raised when the PageSpeed Insights API call fails."""
