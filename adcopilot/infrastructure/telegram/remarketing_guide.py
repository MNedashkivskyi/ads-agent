"""Remarketing tag setup guidance for GROWTH-tier accounts."""

from __future__ import annotations

REMARKETING_GUIDE = """
🔄 *Set up remarketing to re-engage visitors*

98% of visitors don't convert on their first visit\\. Remarketing shows your ads to people who already visited your website\\.

*Step 1: Install the Google Ads tag*
1\\. In Google Ads, go to *Tools → Audience Manager → Your data segments*
2\\. Click *"Set up tag"* → copy the Global Site Tag
3\\. Paste it in your website's `<head>` section \\(or use Google Tag Manager\\)

*Step 2: Create audience lists \\(I'll do this for you\\)*
Once the tag is active for 7\\+ days, I'll automatically create:
• All visitors \\(last 30 days\\)
• High\\-intent visitors \\(pricing/demo/contact page visitors\\)

*Step 3: I'll add remarketing to your campaign*
After lists reach 1,000\\+ users, I'll recommend adding a remarketing campaign\\.

Reply *done* when you've installed the tag, and I'll verify it's working\\.
"""


def get_remarketing_guide() -> str:
    """Return the remarketing tag setup guide (MarkdownV2 format)."""
    return REMARKETING_GUIDE.strip()
