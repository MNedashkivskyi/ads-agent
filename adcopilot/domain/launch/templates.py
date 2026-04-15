"""Vertical fallback templates for campaign proposals.

Used when the LLM pipeline fails twice.  Every template produces a
``CampaignProposal`` that passes the rule-based validator:
  • ≥ 8 keywords per ad group
  • ≥ 3 headlines per ad (all ≤ 30 chars)
  • ≥ 2 descriptions per ad (all ≤ 90 chars)
  • path segments ≤ 15 chars
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from adcopilot.domain.launch.entities import (
    AdGroupProposal,
    AdProposal,
    CampaignBrief,
    CampaignProposal,
    CampaignProposalId,
    KeywordProposal,
    MatchType,
)

# ---------------------------------------------------------------------------
# Internal template data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _KW:
    text: str
    match_type: MatchType = MatchType.PHRASE
    estimated_cpc_pln: float = 1.0


@dataclass(frozen=True)
class _Ad:
    headlines: tuple[str, ...]
    descriptions: tuple[str, ...]
    path1: str = ""
    path2: str = ""


@dataclass(frozen=True)
class _AdGroup:
    name: str
    keywords: tuple[_KW, ...]
    ads: tuple[_Ad, ...]


@dataclass(frozen=True)
class _Template:
    vertical: str
    campaign_name: str
    bidding_strategy: str
    ad_groups: tuple[_AdGroup, ...]
    negatives: tuple[str, ...]


# ---------------------------------------------------------------------------
# Template definitions (all copy validated against character limits)
# ---------------------------------------------------------------------------

_TEMPLATES: dict[str, _Template] = {
    "salon": _Template(
        vertical="salon",
        campaign_name="Hair Salon | Book Appointment",
        bidding_strategy="MAXIMIZE_CONVERSIONS",
        ad_groups=(
            _AdGroup(
                name="Haircuts & Styling",
                keywords=(
                    _KW("hair salon", MatchType.BROAD, 1.2),
                    _KW("haircut near me", MatchType.PHRASE, 1.4),
                    _KW("women haircut", MatchType.PHRASE, 1.0),
                    _KW("men haircut", MatchType.PHRASE, 1.0),
                    _KW("hair styling", MatchType.PHRASE, 0.9),
                    _KW("salon appointment", MatchType.EXACT, 1.8),
                    _KW("best haircut", MatchType.BROAD, 1.1),
                    _KW("affordable haircut", MatchType.PHRASE, 0.8),
                ),
                ads=(
                    _Ad(
                        headlines=("Hair Salon Experts", "Book Your Haircut", "Same Day Available"),
                        descriptions=(
                            "Professional hair salon. Book online for cuts, styling & more.",
                            "Expert stylists ready. Walk-ins welcome, appointments preferred.",
                        ),
                        path1="HairSalon",
                        path2="",
                    ),
                ),
            ),
            _AdGroup(
                name="Hair Coloring",
                keywords=(
                    _KW("hair color salon", MatchType.PHRASE, 2.0),
                    _KW("highlights near me", MatchType.PHRASE, 1.6),
                    _KW("hair balayage", MatchType.PHRASE, 2.5),
                    _KW("ombre hair salon", MatchType.PHRASE, 1.8),
                    _KW("hair dye", MatchType.BROAD, 1.0),
                    _KW("root touch up", MatchType.PHRASE, 1.4),
                    _KW("hair color appointment", MatchType.EXACT, 2.2),
                    _KW("professional coloring", MatchType.PHRASE, 1.5),
                ),
                ads=(
                    _Ad(
                        headlines=("Hair Color Experts", "Book Coloring Today", "Get Your Look Now"),
                        descriptions=(
                            "Hair coloring by trained stylists. Balayage, highlights & more.",
                            "Transform your look with professional hair color services.",
                        ),
                        path1="HairColor",
                        path2="",
                    ),
                ),
            ),
        ),
        negatives=(
            "wigs", "hair extensions amazon", "diy hair color",
            "hair products", "youtube", "free", "tutorial",
        ),
    ),
    "ecommerce": _Template(
        vertical="ecommerce",
        campaign_name="Online Store | Shop Now",
        bidding_strategy="MAXIMIZE_CONVERSIONS",
        ad_groups=(
            _AdGroup(
                name="Shop Products",
                keywords=(
                    _KW("online store", MatchType.BROAD, 0.8),
                    _KW("buy online", MatchType.PHRASE, 1.0),
                    _KW("shop online", MatchType.PHRASE, 0.9),
                    _KW("order online", MatchType.PHRASE, 1.1),
                    _KW("best deals online", MatchType.PHRASE, 1.2),
                    _KW("fast delivery", MatchType.BROAD, 0.7),
                    _KW("free shipping", MatchType.PHRASE, 1.0),
                    _KW("online shopping", MatchType.BROAD, 0.8),
                ),
                ads=(
                    _Ad(
                        headlines=("Shop Online Today", "Fast Delivery", "Best Prices"),
                        descriptions=(
                            "Shop our online store for great products and fast delivery.",
                            "Huge selection, best prices. Order online for quick delivery.",
                        ),
                        path1="ShopNow",
                        path2="",
                    ),
                ),
            ),
            _AdGroup(
                name="Special Offers",
                keywords=(
                    _KW("sale online", MatchType.PHRASE, 0.9),
                    _KW("discount store", MatchType.PHRASE, 1.0),
                    _KW("deals online", MatchType.BROAD, 0.8),
                    _KW("special offer", MatchType.PHRASE, 1.1),
                    _KW("clearance sale", MatchType.PHRASE, 0.7),
                    _KW("best price online", MatchType.PHRASE, 1.2),
                    _KW("save money online", MatchType.BROAD, 0.6),
                    _KW("buy cheap online", MatchType.PHRASE, 0.8),
                ),
                ads=(
                    _Ad(
                        headlines=("Special Offers Today", "Save Up to 50%", "Best Prices Online"),
                        descriptions=(
                            "Great deals on all products. Shop our sale for big savings.",
                            "Exclusive online discounts. Save more when you shop today.",
                        ),
                        path1="Sale",
                        path2="",
                    ),
                ),
            ),
        ),
        negatives=("used", "second hand", "diy", "free", "stolen", "crack"),
    ),
    "restaurant": _Template(
        vertical="restaurant",
        campaign_name="Restaurant | Order or Reserve",
        bidding_strategy="MAXIMIZE_CONVERSIONS",
        ad_groups=(
            _AdGroup(
                name="Dine In",
                keywords=(
                    _KW("restaurant near me", MatchType.PHRASE, 1.0),
                    _KW("best restaurant", MatchType.BROAD, 0.9),
                    _KW("book a table", MatchType.PHRASE, 1.2),
                    _KW("restaurant reservation", MatchType.EXACT, 1.5),
                    _KW("dinner near me", MatchType.PHRASE, 1.1),
                    _KW("lunch restaurant", MatchType.PHRASE, 0.8),
                    _KW("local restaurant", MatchType.BROAD, 0.7),
                    _KW("family restaurant", MatchType.PHRASE, 0.9),
                ),
                ads=(
                    _Ad(
                        headlines=("Reserve Your Table", "Great Food & Service", "Book Online Now"),
                        descriptions=(
                            "Reserve your table online for a great dining experience.",
                            "Fresh ingredients, great atmosphere. Book your table today.",
                        ),
                        path1="Reserve",
                        path2="",
                    ),
                ),
            ),
            _AdGroup(
                name="Takeaway & Delivery",
                keywords=(
                    _KW("food delivery near me", MatchType.PHRASE, 1.0),
                    _KW("takeaway near me", MatchType.PHRASE, 0.9),
                    _KW("order food online", MatchType.PHRASE, 1.1),
                    _KW("food takeout", MatchType.BROAD, 0.8),
                    _KW("fast food delivery", MatchType.PHRASE, 0.7),
                    _KW("restaurant delivery", MatchType.PHRASE, 1.0),
                    _KW("order online food", MatchType.BROAD, 0.8),
                    _KW("home food delivery", MatchType.PHRASE, 0.9),
                ),
                ads=(
                    _Ad(
                        headlines=("Order Food Online", "Fast Delivery", "Fresh Meals"),
                        descriptions=(
                            "Order fresh meals online and enjoy fast delivery to your door.",
                            "Hot food delivered quickly. Order online in just 2 minutes.",
                        ),
                        path1="OrderNow",
                        path2="",
                    ),
                ),
            ),
        ),
        negatives=("recipe", "how to cook", "cooking class", "free food", "food bank"),
    ),
    "legal": _Template(
        vertical="legal",
        campaign_name="Legal Services | Free Consult",
        bidding_strategy="MAXIMIZE_CONVERSIONS",
        ad_groups=(
            _AdGroup(
                name="Legal Advice",
                keywords=(
                    _KW("lawyer near me", MatchType.PHRASE, 3.0),
                    _KW("legal advice", MatchType.PHRASE, 2.5),
                    _KW("attorney consultation", MatchType.EXACT, 3.5),
                    _KW("legal services", MatchType.BROAD, 2.0),
                    _KW("solicitor near me", MatchType.PHRASE, 2.8),
                    _KW("law firm", MatchType.PHRASE, 2.2),
                    _KW("free legal advice", MatchType.PHRASE, 2.0),
                    _KW("legal consultation", MatchType.PHRASE, 2.6),
                ),
                ads=(
                    _Ad(
                        headlines=("Expert Legal Advice", "Free Consultation", "Trusted Lawyers"),
                        descriptions=(
                            "Experienced lawyers ready to help. Book a free consultation today.",
                            "Get expert legal advice from trusted solicitors. Contact us now.",
                        ),
                        path1="LegalHelp",
                        path2="",
                    ),
                ),
            ),
            _AdGroup(
                name="Case Representation",
                keywords=(
                    _KW("legal representation", MatchType.PHRASE, 3.5),
                    _KW("court representation", MatchType.EXACT, 4.0),
                    _KW("legal case help", MatchType.PHRASE, 2.8),
                    _KW("defense lawyer", MatchType.PHRASE, 3.2),
                    _KW("civil case lawyer", MatchType.PHRASE, 3.0),
                    _KW("legal support", MatchType.BROAD, 1.8),
                    _KW("lawsuit help", MatchType.PHRASE, 2.5),
                    _KW("win your case", MatchType.BROAD, 2.0),
                ),
                ads=(
                    _Ad(
                        headlines=("Fight Your Case", "Legal Experts", "Win With Us"),
                        descriptions=(
                            "Experienced legal team to represent you in court. Call today.",
                            "We handle your case from start to finish. No win, no fee.",
                        ),
                        path1="CaseHelp",
                        path2="",
                    ),
                ),
            ),
        ),
        negatives=("diy legal", "free template", "legal form", "law school", "paralegal course"),
    ),
    "medical": _Template(
        vertical="medical",
        campaign_name="Medical Clinic | Book Appointment",
        bidding_strategy="MAXIMIZE_CONVERSIONS",
        ad_groups=(
            _AdGroup(
                name="Appointments",
                keywords=(
                    _KW("doctor near me", MatchType.PHRASE, 2.0),
                    _KW("medical appointment", MatchType.PHRASE, 2.5),
                    _KW("clinic near me", MatchType.BROAD, 1.5),
                    _KW("GP appointment", MatchType.EXACT, 2.8),
                    _KW("book a doctor", MatchType.PHRASE, 2.2),
                    _KW("health clinic", MatchType.PHRASE, 1.8),
                    _KW("private doctor", MatchType.PHRASE, 2.4),
                    _KW("medical consultation", MatchType.PHRASE, 2.6),
                ),
                ads=(
                    _Ad(
                        headlines=("Book an Appointment", "Trusted Doctors", "Same Day Available"),
                        descriptions=(
                            "Book a medical appointment online. Same-day slots available.",
                            "Experienced doctors, caring staff. Your health is our priority.",
                        ),
                        path1="BookNow",
                        path2="",
                    ),
                ),
            ),
            _AdGroup(
                name="Specialist Services",
                keywords=(
                    _KW("specialist doctor", MatchType.PHRASE, 3.0),
                    _KW("specialist referral", MatchType.PHRASE, 2.8),
                    _KW("private specialist", MatchType.PHRASE, 3.2),
                    _KW("medical specialist", MatchType.BROAD, 2.5),
                    _KW("specialist clinic", MatchType.PHRASE, 2.6),
                    _KW("consultant appointment", MatchType.EXACT, 3.5),
                    _KW("private consultation", MatchType.PHRASE, 2.8),
                    _KW("health specialist", MatchType.PHRASE, 2.2),
                ),
                ads=(
                    _Ad(
                        headlines=("Specialist Care", "Expert Consultants", "Fast Appointments"),
                        descriptions=(
                            "See a specialist fast. Private consultations available now.",
                            "Expert medical consultants. Book your appointment online today.",
                        ),
                        path1="Specialist",
                        path2="",
                    ),
                ),
            ),
        ),
        negatives=("home remedy", "self-diagnosis", "medical school", "free medicine", "drug"),
    ),
    "generic": _Template(
        vertical="generic",
        campaign_name="Quality Services | Contact Us",
        bidding_strategy="MAXIMIZE_CONVERSIONS",
        ad_groups=(
            _AdGroup(
                name="Main Services",
                keywords=(
                    _KW("services near me", MatchType.PHRASE, 1.0),
                    _KW("best services", MatchType.BROAD, 0.8),
                    _KW("professional service", MatchType.PHRASE, 1.2),
                    _KW("local services", MatchType.BROAD, 0.9),
                    _KW("contact us today", MatchType.PHRASE, 0.7),
                    _KW("get a quote", MatchType.PHRASE, 1.5),
                    _KW("free estimate", MatchType.PHRASE, 1.1),
                    _KW("affordable services", MatchType.PHRASE, 1.0),
                ),
                ads=(
                    _Ad(
                        headlines=("Quality Services", "Get a Free Quote", "Contact Us Today"),
                        descriptions=(
                            "Professional services at great prices. Contact us for a quote.",
                            "Trusted local experts. Get your free estimate today.",
                        ),
                        path1="Services",
                        path2="",
                    ),
                ),
            ),
            _AdGroup(
                name="Get in Touch",
                keywords=(
                    _KW("contact us", MatchType.PHRASE, 0.8),
                    _KW("call us today", MatchType.PHRASE, 0.9),
                    _KW("book now", MatchType.PHRASE, 1.2),
                    _KW("schedule appointment", MatchType.PHRASE, 1.0),
                    _KW("get in touch", MatchType.BROAD, 0.7),
                    _KW("customer service", MatchType.BROAD, 0.8),
                    _KW("request a callback", MatchType.PHRASE, 1.1),
                    _KW("speak to an expert", MatchType.PHRASE, 1.3),
                ),
                ads=(
                    _Ad(
                        headlines=("Speak to an Expert", "Book Your Session", "Call Us Today"),
                        descriptions=(
                            "Ready to help. Contact our friendly team for expert advice.",
                            "Book your appointment now. Fast response guaranteed.",
                        ),
                        path1="Contact",
                        path2="",
                    ),
                ),
            ),
        ),
        negatives=("free", "diy", "tutorial", "youtube", "how to"),
    ),
}

# ---------------------------------------------------------------------------
# Vertical detection (keyword-based)
# ---------------------------------------------------------------------------

_VERTICAL_KEYWORDS: dict[str, list[str]] = {
    "salon": ["salon", "hair", "beauty", "spa", "nail", "makeup", "hairdress", "barber"],
    "ecommerce": [
        "shop", "store", "buy", "sell", "product", "online shop",
        "ecommerce", "e-commerce", "delivery", "order online",
    ],
    "restaurant": [
        "restaurant", "cafe", "food", "eat", "meal", "pizza",
        "bar", "bistro", "diner", "takeaway", "delivery food",
    ],
    "legal": ["lawyer", "legal", "attorney", "law firm", "solicitor", "barrister", "court"],
    "medical": [
        "doctor", "medical", "clinic", "dentist", "health", "hospital",
        "physician", "nurse", "therapy", "treatment",
    ],
}


def detect_vertical_from_description(business_description: str) -> str:
    """Return the best-matching vertical name for *business_description*."""
    desc = business_description.lower()
    scores: dict[str, int] = {v: 0 for v in _VERTICAL_KEYWORDS}
    for vertical, keywords in _VERTICAL_KEYWORDS.items():
        for kw in keywords:
            if kw in desc:
                scores[vertical] += 1
    best = max(scores, key=lambda v: scores[v])
    return best if scores[best] > 0 else "generic"


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------


def build_proposal_from_template(brief: CampaignBrief) -> CampaignProposal:
    """Build a valid ``CampaignProposal`` from the best-matching vertical template."""
    vertical_key = detect_vertical_from_description(brief.business_description)
    tmpl = _TEMPLATES.get(vertical_key, _TEMPLATES["generic"])

    daily_budget_micros = int(brief.monthly_budget_pln / Decimal("30") * Decimal("1000000"))

    ad_groups: list[AdGroupProposal] = []
    for ag_tmpl in tmpl.ad_groups:
        keywords = [
            KeywordProposal(
                text=kw.text,
                match_type=kw.match_type,
                estimated_cpc_micros=int(kw.estimated_cpc_pln * 1_000_000),
            )
            for kw in ag_tmpl.keywords
        ]
        ads = [
            AdProposal(
                headlines=list(ad.headlines),
                descriptions=list(ad.descriptions),
                final_url="https://example.com",
                path_segments=(ad.path1, ad.path2),
            )
            for ad in ag_tmpl.ads
        ]
        ad_groups.append(AdGroupProposal(name=ag_tmpl.name, keywords=keywords, ads=ads))

    all_cpcs = [kw.estimated_cpc_micros for ag in ad_groups for kw in ag.keywords]
    negatives = list(tmpl.negatives) + brief.exclusions

    return CampaignProposal(
        id=CampaignProposalId(str(uuid.uuid4())),
        brief_id=brief.id,
        campaign_name=tmpl.campaign_name,
        daily_budget_micros=daily_budget_micros,
        location_targeting=brief.location,
        bidding_strategy=tmpl.bidding_strategy,
        ad_groups=ad_groups,
        negative_keywords=negatives,
        estimated_cpc_range=(
            min(all_cpcs) if all_cpcs else 500_000,
            max(all_cpcs) if all_cpcs else 2_000_000,
        ),
        generated_at=datetime.now(UTC),
    )
