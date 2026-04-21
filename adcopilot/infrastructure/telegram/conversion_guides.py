"""Goal-specific conversion tracking setup guides sent via Telegram post-launch."""

from __future__ import annotations

CONVERSION_GUIDES: dict[str, str] = {
    "Call": (
        "📞 *Set up call tracking*\n\n"
        "1. In Google Ads → Goals → Conversions → ✚ New conversion action\n"
        "2. Choose *Phone calls* → Calls from ads using a Google forwarding number\n"
        "3. Set minimum call duration (e.g. 60 seconds)\n"
        "4. Save and apply to your campaign\n\n"
        "Once active, your bidding strategy will automatically upgrade when enough data is collected."
    ),
    "Book": (
        "📋 *Set up booking tracking*\n\n"
        "1. In Google Ads → Goals → Conversions → ✚ New conversion action\n"
        "2. Choose *Website* → add your booking confirmation page URL\n"
        "3. Copy the Google tag snippet and add it to your booking confirmation page\n"
        "4. Verify the tag is firing using Google Tag Assistant\n\n"
        "Once active, your bidding strategy will automatically upgrade when enough data is collected."
    ),
    "Purchase": (
        "🛒 *Set up purchase tracking*\n\n"
        "1. In Google Ads → Goals → Conversions → ✚ New conversion action\n"
        "2. Choose *Website* → select *Purchase* category\n"
        "3. Add your order confirmation page URL or use Google Tag Manager\n"
        "4. Optionally add dynamic conversion value (order total) for ROAS bidding\n\n"
        "Once active, your bidding strategy will automatically upgrade when enough data is collected."
    ),
    "Visit website": (
        "🌐 *Set up page visit tracking*\n\n"
        "1. In Google Ads → Goals → Conversions → ✚ New conversion action\n"
        "2. Choose *Website* → select *Page view* category\n"
        "3. Add your key destination page URL (e.g. contact page, service page)\n"
        "4. Install the Google tag in your website's <head> section\n\n"
        "Once active, your bidding strategy will automatically upgrade when enough data is collected."
    ),
    "Sign up": (
        "✍️ *Set up signup tracking*\n\n"
        "1. In Google Ads → Goals → Conversions → ✚ New conversion action\n"
        "2. Choose *Website* → select *Sign-up* category\n"
        "3. Add your signup confirmation page URL\n"
        "4. Install the Google tag or use Google Tag Manager\n\n"
        "Once active, your bidding strategy will automatically upgrade when enough data is collected."
    ),
}

_DEFAULT_GUIDE = (
    "⚙️ *Set up conversion tracking*\n\n"
    "1. In Google Ads → Goals → Conversions → ✚ New conversion action\n"
    "2. Choose *Website* and follow the setup wizard\n"
    "3. Install the Google tag on your website's thank-you or confirmation page\n\n"
    "Once active, your bidding strategy will automatically upgrade when enough data is collected."
)


def get_conversion_guide(primary_action: str) -> str:
    """Return a goal-specific conversion tracking setup guide."""
    return CONVERSION_GUIDES.get(primary_action, _DEFAULT_GUIDE)
