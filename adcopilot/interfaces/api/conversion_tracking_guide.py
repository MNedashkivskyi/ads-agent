"""GET /api/conversion-tracking/guide — setup instructions by platform."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/conversion-tracking", tags=["conversion-tracking"])

_GUIDES: dict[str, dict] = {
    "wordpress": {
        "platform": "wordpress",
        "display_name": "WordPress",
        "steps": [
            {
                "step": 1,
                "title": "Zainstaluj wtyczkę Google Site Kit",
                "description": (
                    "W panelu WordPress przejdź do Wtyczki → Dodaj nową, "
                    "wyszukaj 'Site Kit by Google' i kliknij Zainstaluj."
                ),
            },
            {
                "step": 2,
                "title": "Połącz konto Google Ads",
                "description": (
                    "Po aktywacji Site Kit kliknij 'Rozpocznij konfigurację' "
                    "i zaloguj się na konto Google powiązane z Google Ads."
                ),
            },
            {
                "step": 3,
                "title": "Włącz śledzenie konwersji",
                "description": (
                    "W Google Ads przejdź do Narzędzia → Pomiar → Konwersje. "
                    "Utwórz nową konwersję (np. 'Formularz kontaktowy') "
                    "i skopiuj tag konwersji."
                ),
            },
            {
                "step": 4,
                "title": "Dodaj tag do strony z podziękowaniem",
                "description": (
                    "Umieść tag zdarzenia konwersji na stronie wyświetlanej "
                    "po wysłaniu formularza (np. /dziekujemy). "
                    "Site Kit automatycznie doda tag globalny (gtag.js)."
                ),
            },
            {
                "step": 5,
                "title": "Zweryfikuj konfigurację",
                "description": (
                    "Użyj rozszerzenia Tag Assistant (Chrome), "
                    "wypełnij formularz na stronie testowej "
                    "i sprawdź, czy konwersja pojawia się w Google Ads (do 24h)."
                ),
            },
        ],
        "estimated_minutes": 15,
        "help_url": "https://support.google.com/google-ads/answer/6095821",
    },
    "wix": {
        "platform": "wix",
        "display_name": "Wix",
        "steps": [
            {
                "step": 1,
                "title": "Otwórz panel marketing w Wix",
                "description": (
                    "Zaloguj się do Wix i przejdź do Marketing & SEO → "
                    "Google Ads w lewym menu panelu."
                ),
            },
            {
                "step": 2,
                "title": "Połącz konto Google Ads",
                "description": (
                    "Kliknij 'Połącz' i wybierz konto Google Ads. "
                    "Wix automatycznie doda globalny tag Google (gtag.js) do całej strony."
                ),
            },
            {
                "step": 3,
                "title": "Utwórz konwersję w Google Ads",
                "description": (
                    "W Google Ads przejdź do Narzędzia → Konwersje → + Nowa konwersja. "
                    "Wybierz 'Witryna internetowa' i skonfiguruj zdarzenie "
                    "(np. odwiedziny strony z podziękowaniem)."
                ),
            },
            {
                "step": 4,
                "title": "Dodaj tag zdarzenia przez Wix",
                "description": (
                    "W Wix Editor przejdź do strony z podziękowaniem. "
                    "Dodaj element HTML z kodem tagu zdarzenia konwersji "
                    "skopiowanym z Google Ads."
                ),
            },
            {
                "step": 5,
                "title": "Przetestuj śledzenie",
                "description": (
                    "Opublikuj stronę i wypełnij formularz testowo. "
                    "W Google Ads sprawdź zakładkę Konwersje — "
                    "nowe konwersje pojawiają się do 24 godzin."
                ),
            },
        ],
        "estimated_minutes": 20,
        "help_url": "https://support.wix.com/en/article/connecting-google-ads-to-your-wix-site",
    },
    "squarespace": {
        "platform": "squarespace",
        "display_name": "Squarespace",
        "steps": [
            {
                "step": 1,
                "title": "Przejdź do ustawień zewnętrznych usług",
                "description": (
                    "W panelu Squarespace kliknij Ustawienia → "
                    "Zewnętrzne usługi → Google Ads."
                ),
            },
            {
                "step": 2,
                "title": "Wprowadź identyfikator konwersji",
                "description": (
                    "W Google Ads stwórz nową konwersję (Narzędzia → Konwersje). "
                    "Skopiuj ID konwersji (AW-XXXXXXXXX) i wklej w Squarespace."
                ),
            },
            {
                "step": 3,
                "title": "Włącz śledzenie zamówień (e-commerce)",
                "description": (
                    "Jeśli prowadzisz sklep: w Squarespace włącz opcję "
                    "'Śledzenie konwersji zakupu'. "
                    "Squarespace automatycznie wyśle wartość transakcji do Google Ads."
                ),
            },
            {
                "step": 4,
                "title": "Skonfiguruj konwersję formularza",
                "description": (
                    "Dla konwersji formularzy kontaktowych: "
                    "utwórz w Google Ads konwersję typu 'Strona' "
                    "z URL strony z podziękowaniem (np. /kontakt?submitted=true)."
                ),
            },
            {
                "step": 5,
                "title": "Sprawdź status w Google Ads",
                "description": (
                    "Po 48 godzinach od pierwszego ruchu sprawdź status "
                    "w Google Ads → Narzędzia → Konwersje. "
                    "Status 'Rejestrowanie' oznacza poprawną konfigurację."
                ),
            },
        ],
        "estimated_minutes": 15,
        "help_url": "https://support.squarespace.com/hc/en-us/articles/205814858",
    },
    "other": {
        "platform": "other",
        "display_name": "Inna platforma / HTML",
        "steps": [
            {
                "step": 1,
                "title": "Pobierz globalny tag Google z Google Ads",
                "description": (
                    "W Google Ads przejdź do Narzędzia → Konwersje. "
                    "Utwórz nową konwersję i pobierz globalny tag Google (gtag.js)."
                ),
            },
            {
                "step": 2,
                "title": "Dodaj tag do sekcji <head> wszystkich stron",
                "description": (
                    "Wklej kod tagu globalnego (snippet z 'Global site tag') "
                    "bezpośrednio przed zamknięciem tagu </head> "
                    "na każdej stronie serwisu."
                ),
            },
            {
                "step": 3,
                "title": "Dodaj tag zdarzenia na stronie z podziękowaniem",
                "description": (
                    "Na stronie wyświetlanej po wypełnieniu formularza "
                    "lub zakupie dodaj kod zdarzenia konwersji "
                    "('event snippet') z Google Ads."
                ),
            },
            {
                "step": 4,
                "title": "Zweryfikuj przez Google Tag Assistant",
                "description": (
                    "Zainstaluj rozszerzenie Tag Assistant Legacy (Chrome), "
                    "odwiedź stronę i sprawdź, czy tag Google Ads jest wykryty "
                    "bez błędów."
                ),
            },
            {
                "step": 5,
                "title": "Monitoruj konwersje w Google Ads",
                "description": (
                    "Wykonaj testową konwersję (wyślij formularz, "
                    "wykonaj zakup testowy). "
                    "W Google Ads konwersja pojawi się w ciągu 24 godzin."
                ),
            },
        ],
        "estimated_minutes": 30,
        "help_url": "https://support.google.com/google-ads/answer/6095821",
    },
}

_PLATFORMS = list(_GUIDES.keys())


class TrackingStep(BaseModel):
    step: int
    title: str
    description: str


class TrackingGuideResponse(BaseModel):
    platform: str
    display_name: str
    steps: list[TrackingStep]
    estimated_minutes: int
    help_url: str


class TrackingGuideSummary(BaseModel):
    platform: str
    display_name: str
    estimated_minutes: int


@router.get("/guide", response_model=list[TrackingGuideSummary])
async def list_tracking_guide_platforms() -> list[TrackingGuideSummary]:
    """Return available platform options for the setup guide."""
    return [
        TrackingGuideSummary(
            platform=p,
            display_name=_GUIDES[p]["display_name"],
            estimated_minutes=_GUIDES[p]["estimated_minutes"],
        )
        for p in _PLATFORMS
    ]


@router.get("/guide/{platform}", response_model=TrackingGuideResponse)
async def get_tracking_guide(platform: str) -> TrackingGuideResponse:
    """Return step-by-step conversion tracking setup instructions for a platform.

    Supported platforms: wordpress, wix, squarespace, other.
    """
    from fastapi import HTTPException

    guide = _GUIDES.get(platform)
    if guide is None:
        raise HTTPException(
            status_code=404,
            detail=f"Guide not found for platform '{platform}'. Use one of: {', '.join(_PLATFORMS)}",
        )
    return TrackingGuideResponse(**guide)
