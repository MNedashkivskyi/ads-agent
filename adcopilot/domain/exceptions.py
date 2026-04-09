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
