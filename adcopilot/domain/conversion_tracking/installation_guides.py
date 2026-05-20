"""Platform-specific conversion tracking installation guides in Polish."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GuideStep:
    step: int
    title: str
    description: str
    is_verify: bool = False
    screenshot_hint_pl: str | None = None
    gtm_import_instruction_pl: str | None = None


@dataclass
class InstallationGuide:
    platform: str
    platform_label: str
    steps: list[GuideStep] = field(default_factory=list)
    gtm_container_hint: str | None = None
    gtm_container_download_url: str | None = None


_GUIDES: dict[str, InstallationGuide] = {
    "wordpress": InstallationGuide(
        platform="wordpress",
        platform_label="WordPress",
        steps=[
            GuideStep(
                step=1,
                title="Pobierz gotowy kontener GTM",
                description=(
                    "Kliknij przycisk 'Pobierz kontener GTM' powyżej. "
                    "Plik JSON zawiera skonfigurowane tagi konwersji Google Ads."
                ),
                screenshot_hint_pl="Przycisk pobierania znajduje się w sekcji 'Instalacja' powyżej.",
                gtm_import_instruction_pl=(
                    "W GTM: Administrator → Importuj kontener → wybierz pobrany plik JSON → "
                    "Scal → Potwierdź import."
                ),
            ),
            GuideStep(
                step=2,
                title="Zainstaluj wtyczkę Google Tag Manager",
                description=(
                    "W panelu WordPress przejdź do Wtyczki → Dodaj nową. "
                    "Wyszukaj 'Google Tag Manager for WordPress' (autor: Thomas Geiger) i zainstaluj."
                ),
                screenshot_hint_pl="Szukaj 'GTM4WP' w katalogu wtyczek WordPress.",
            ),
            GuideStep(
                step=3,
                title="Wklej ID kontenera GTM",
                description=(
                    "Przejdź do Ustawienia → Google Tag Manager. "
                    "Wklej ID kontenera GTM (format: GTM-XXXXXXX) i zapisz."
                ),
                screenshot_hint_pl="ID kontenera znajdziesz w nagłówku panelu GTM obok nazwy konta.",
            ),
            GuideStep(
                step=4,
                title="Opublikuj kontener GTM",
                description="W GTM kliknij 'Opublikuj' i nadaj wersji nazwę np. 'Śledzenie konwersji Google Ads'.",
                screenshot_hint_pl="Przycisk 'Prześlij' (Submit) jest w prawym górnym rogu GTM.",
            ),
            GuideStep(
                step=5,
                title="Zweryfikuj instalację",
                description=(
                    "Wejdź na swoją stronę i sprawdź w Google Tag Assistant "
                    "czy tag GTM jest aktywny. Następnie kliknij 'Zweryfikuj' poniżej."
                ),
                is_verify=True,
                screenshot_hint_pl="Tag Assistant pokaże zielony znacznik przy tagu GTM.",
            ),
        ],
        gtm_container_hint="Zainstaluj GTM przez wtyczkę, nie przez ręczną edycję motywu.",
    ),
    "woocommerce": InstallationGuide(
        platform="woocommerce",
        platform_label="WooCommerce",
        steps=[
            GuideStep(
                step=1,
                title="Zainstaluj wtyczkę Google Tag Manager",
                description=(
                    "W panelu WordPress przejdź do Wtyczki → Dodaj nową. "
                    "Wyszukaj 'Google Tag Manager for WordPress' i zainstaluj."
                ),
            ),
            GuideStep(
                step=2,
                title="Wklej ID kontenera GTM",
                description=(
                    "Przejdź do Ustawienia → Google Tag Manager. "
                    "Wklej ID kontenera GTM (format: GTM-XXXXXXX) i zapisz."
                ),
            ),
            GuideStep(
                step=3,
                title="Dodaj tag konwersji dla zakupów",
                description=(
                    "W GTM dodaj tag 'Konwersja Google Ads'. "
                    "Jako wyzwalacz wybierz stronę potwierdzenia zamówienia WooCommerce "
                    "(URL zawiera /order-received/ lub /zamowienie-przyjete/)."
                ),
            ),
            GuideStep(
                step=4,
                title="Opublikuj kontener GTM",
                description="W GTM kliknij 'Opublikuj' i nadaj wersji nazwę.",
            ),
            GuideStep(
                step=5,
                title="Zweryfikuj instalację",
                description="Złóż testowe zamówienie i sprawdź czy konwersja jest rejestrowana. Następnie kliknij 'Zweryfikuj'.",
                is_verify=True,
            ),
        ],
    ),
    "shopify": InstallationGuide(
        platform="shopify",
        platform_label="Shopify",
        steps=[
            GuideStep(
                step=1,
                title="Przejdź do ustawień klienta",
                description="W panelu Shopify przejdź do Ustawienia → Klienci → Zdarzenia klienta.",
            ),
            GuideStep(
                step=2,
                title="Dodaj piksel Google Ads",
                description=(
                    "Kliknij 'Dodaj piksel'. Wybierz 'Google Ads' lub 'Niestandardowy piksel'. "
                    "Wklej kod tagu Google (gtag.js) z ID konwersji Google Ads."
                ),
            ),
            GuideStep(
                step=3,
                title="Skonfiguruj zdarzenie konwersji",
                description=(
                    "W kodzie piksela skonfiguruj zdarzenie 'purchase' jako konwersję Google Ads. "
                    "Shopify automatycznie wywoła piksel na stronie potwierdzenia zamówienia."
                ),
            ),
            GuideStep(
                step=4,
                title="Zapisz i opublikuj",
                description="Zapisz piksel. Shopify automatycznie wdroży go na Twój sklep.",
            ),
            GuideStep(
                step=5,
                title="Zweryfikuj instalację",
                description="Złóż testowe zamówienie i sprawdź raport konwersji w Google Ads po 24h. Kliknij 'Zweryfikuj'.",
                is_verify=True,
            ),
        ],
    ),
    "shoper": InstallationGuide(
        platform="shoper",
        platform_label="Shoper",
        steps=[
            GuideStep(
                step=1,
                title="Pobierz gotowy kontener GTM",
                description=(
                    "Kliknij przycisk 'Pobierz kontener GTM'. "
                    "Plik zawiera tagi konwersji skonfigurowane dla e-commerce Shoper."
                ),
                gtm_import_instruction_pl=(
                    "W GTM: Administrator → Importuj kontener → wybierz pobrany plik → "
                    "Scal → Potwierdź. Uzupełnij ID konwersji w tagu."
                ),
            ),
            GuideStep(
                step=2,
                title="Przejdź do integracji w Shoper",
                description="W panelu Shoper przejdź do Panel → Integracje → Google Tag Manager.",
                screenshot_hint_pl="Sekcja 'Integracje' w lewym menu panelu administracyjnego Shoper.",
            ),
            GuideStep(
                step=3,
                title="Wklej ID kontenera GTM",
                description=(
                    "W polu 'ID kontenera GTM' wklej swój identyfikator (format: GTM-XXXXXXX). "
                    "Zapisz ustawienia."
                ),
                screenshot_hint_pl="ID kontenera GTM znajdziesz na stronie tagmanager.google.com.",
            ),
            GuideStep(
                step=4,
                title="Opublikuj kontener GTM",
                description="W GTM kliknij 'Opublikuj' i nadaj wersji nazwę.",
                screenshot_hint_pl="Przycisk 'Prześlij' w prawym górnym rogu GTM.",
            ),
            GuideStep(
                step=5,
                title="Zweryfikuj instalację",
                description="Złóż testowe zamówienie i sprawdź czy konwersja jest rejestrowana. Kliknij 'Zweryfikuj'.",
                is_verify=True,
            ),
        ],
    ),
    "custom": InstallationGuide(
        platform="custom",
        platform_label="Strona niestandardowa",
        steps=[
            GuideStep(
                step=1,
                title="Utwórz konto Google Tag Manager",
                description="Wejdź na tagmanager.google.com i utwórz konto oraz kontener dla swojej domeny.",
            ),
            GuideStep(
                step=2,
                title="Zainstaluj kod GTM na stronie",
                description=(
                    "Wklej kod GTM w sekcji <head> i <body> każdej strony. "
                    "Poproś swojego dewelopera o dodanie kodu GTM do szablonu strony."
                ),
            ),
            GuideStep(
                step=3,
                title="Skonfiguruj tag konwersji Google Ads",
                description=(
                    "W GTM dodaj nowy tag typu 'Konwersja Google Ads'. "
                    "Ustaw ID konwersji i etykietę z konta Google Ads. "
                    "Wyzwalacz: strona potwierdzenia zakupu/kontaktu."
                ),
            ),
            GuideStep(
                step=4,
                title="Opublikuj kontener GTM",
                description="W GTM kliknij 'Opublikuj' i nadaj wersji nazwę.",
            ),
            GuideStep(
                step=5,
                title="Zweryfikuj instalację",
                description=(
                    "Użyj rozszerzenia Google Tag Assistant w Chrome aby potwierdzić "
                    "że tag działa poprawnie. Następnie kliknij 'Zweryfikuj'."
                ),
                is_verify=True,
            ),
        ],
    ),
}


def get_guide(platform: str) -> InstallationGuide:
    return _GUIDES.get(platform, _GUIDES["custom"])
