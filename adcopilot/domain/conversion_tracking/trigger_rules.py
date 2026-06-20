"""Map a Google Ads conversion-action *category* to a GTM trigger strategy.

The premium GTM generator builds one tag + trigger per enabled conversion
action. Google Ads tells us each action's ``category`` (PURCHASE, LEAD, SIGNUP,
PHONE_CALL_LEAD, DOWNLOAD, PAGE_VIEW, …). This module turns that category — plus
the detected platform and the account's landing-page paths — into a concrete
trigger strategy with a smart default and a flag for whether the user still has
to supply a site-specific detail GTM can't infer (e.g. the success-page URL).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit


class TriggerKind(StrEnum):
    """The kind of GTM trigger generated for a conversion action."""

    PAGE_URL_CONTAINS = "page_url_contains"  # PAGEVIEW filtered on Page URL
    FORM_SUBMISSION = "form_submission"  # GTM Form Submission trigger
    TEL_CLICK = "tel_click"  # LINK_CLICK on a tel: link — fully automatic
    FILE_DOWNLOAD_CLICK = "file_download_click"  # LINK_CLICK on a file link — automatic


@dataclass(frozen=True)
class TriggerStrategy:
    """A proposed trigger for one conversion action."""

    kind: TriggerKind
    # True when the trigger needs a site-specific value the machine can't infer
    # (e.g. which URL means "registration complete"). The guided wizard step asks
    # the user; until then the container ships a clearly-fake placeholder.
    needs_user_input: bool
    # For PAGE_URL_CONTAINS: the URL fragment to match (e.g. "order-received").
    # Empty when we have no confident default and must ask the user.
    default_hint: str = ""


# Google Ads conversion_action.category enum values, grouped by intent.
_PURCHASE = {"PURCHASE", "SUBSCRIBE_PAID", "STORE_SALE", "ADD_TO_CART", "BEGIN_CHECKOUT"}
_LEAD = {
    "LEAD",
    "SUBMIT_LEAD_FORM",
    "IMPORTED_LEAD",
    "QUALIFIED_LEAD",
    "CONVERTED_LEAD",
    "CONTACT",
    "REQUEST_QUOTE",
    "BOOK_APPOINTMENT",
}
_DOWNLOAD = {"DOWNLOAD"}

# Platform → URL fragment that marks a completed purchase ("thank you" page).
_PURCHASE_PATH_BY_PLATFORM = {
    "woocommerce": "order-received",
    "shopify": "thank_you",
}

# Common success-page fragments to look for in the account's landing-page paths
# when we have no platform default (covers PL + EN sites).
_SUCCESS_FRAGMENTS = (
    "thank-you",
    "thank_you",
    "thankyou",
    "dziekujemy",
    "dziekuje",
    "podziekowanie",
    "potwierdzenie",
    "order-received",
    "order-confirmation",
    "success",
)


def _success_fragment_from_urls(final_urls: list[str]) -> str:
    """Return a success-page fragment found in any landing-page path, or ""."""
    for url in final_urls:
        path = urlsplit(url).path.lower()
        for fragment in _SUCCESS_FRAGMENTS:
            if fragment in path:
                return fragment
    return ""


def strategy_for_category(
    category: str,
    platform: str,
    final_urls: list[str] | None = None,
) -> TriggerStrategy:
    """Pick a trigger strategy for a conversion ``category`` on ``platform``."""
    cat = (category or "").strip().upper()
    urls = final_urls or []

    # Phone calls: a click on a tel: link — no site knowledge required.
    if "PHONE_CALL" in cat:
        return TriggerStrategy(TriggerKind.TEL_CLICK, needs_user_input=False)

    # File downloads: a click on a file link — automatic.
    if cat in _DOWNLOAD:
        return TriggerStrategy(TriggerKind.FILE_DOWNLOAD_CLICK, needs_user_input=False)

    # Lead-gen: a form submission is the sane default; the user can switch it to
    # a success-URL in the guided step.
    if cat in _LEAD:
        return TriggerStrategy(TriggerKind.FORM_SUBMISSION, needs_user_input=False)

    # Purchases: prefer the platform's known order-confirmation path; otherwise
    # fall back to a success fragment in the landing-page paths; else ask.
    if cat in _PURCHASE:
        hint = _PURCHASE_PATH_BY_PLATFORM.get(platform, "") or _success_fragment_from_urls(urls)
        return TriggerStrategy(
            TriggerKind.PAGE_URL_CONTAINS,
            needs_user_input=hint == "",
            default_hint=hint,
        )

    # SIGNUP, PAGE_VIEW, DEFAULT and anything unmapped: a specific success page.
    # Use a fragment from the landing paths if one is obvious, else ask the user.
    hint = _success_fragment_from_urls(urls)
    return TriggerStrategy(
        TriggerKind.PAGE_URL_CONTAINS,
        needs_user_input=hint == "",
        default_hint=hint,
    )
