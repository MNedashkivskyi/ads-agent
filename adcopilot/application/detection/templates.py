"""Prompt templates and formatting helpers for the recommendation explainer."""

from __future__ import annotations

from adcopilot.domain.recommendation import RecommendationKind

SYSTEM_PROMPT = """
You are an assistant that explains Google Ads recommendations to small business owners.
Rules you MUST follow:
- Write your ENTIRE answer in the language specified in the user message. Never mix languages — every word, including the closing sentence, must be in that one language.
- Use plain language, no PPC or marketing jargon
- Return plain text only. Do NOT use any markdown: no headings, no "#", no "*", no bullet points, no bold, no backticks.
- Do NOT add a title or heading. Start directly with the first sentence.
- Always lead with the money impact in the user's currency (use the provided savings figure)
- Maximum 4 sentences total
- Finish with exactly one sentence explaining what will happen after the user approves the action, written in the SAME language as the rest of the answer.
- Never output placeholder tokens such as {name} or {campaign}. If a detail is missing, leave it out naturally instead of showing the placeholder.
- Do NOT invent new actions — only explain the action provided to you
"""

TEMPLATES: dict[RecommendationKind, dict[str, str]] = {
    RecommendationKind.ADD_NEGATIVE_KEYWORD: {
        "pl": (
            "Twoja reklama wyświetliła się na frazę '{search_term}', która wygenerowała"
            " {clicks} kliknięć za {cost} i 0 konwersji. To typowe słowo niezwiązane z Twoją"
            " ofertą. Szacowane oszczędności: {savings}/miesiąc. Możliwe działanie: dodanie"
            " '{search_term}' jako słowa wykluczonego. Wytłumacz jak to działa prostym językiem."
            " Odpowiedz po polsku."
        ),
        "en": (
            "Your ad showed for '{search_term}' which got {clicks} clicks costing {cost} with"
            " 0 conversions. This is likely an irrelevant query. Estimated savings:"
            " {savings}/month. Action: add '{search_term}' as a negative keyword. Explain how"
            " this helps in plain English."
        ),
    },
    RecommendationKind.PAUSE_KEYWORD: {
        "pl": (
            "Słowo kluczowe '{keyword}' wydało {cost} przy {clicks} kliknięciach i 0"
            " konwersjach w ostatnich 30 dniach. Szacowane oszczędności: {savings}/miesiąc."
            " Możliwe działanie: wstrzymanie tego słowa kluczowego. Wytłumacz krótko po polsku."
        ),
        "en": (
            "Keyword '{keyword}' spent {cost} with {clicks} clicks and 0 conversions in the"
            " last 30 days. Estimated savings: {savings}/month. Action: pause this keyword."
            " Explain briefly in plain English."
        ),
    },
    RecommendationKind.PAUSE_AD: {
        "pl": (
            "Reklama wydała {cost} z minimalnym efektem. Szacowane oszczędności:"
            " {savings}/miesiąc. Możliwe działanie: wstrzymanie tej reklamy. Wytłumacz krótko"
            " po polsku."
        ),
        "en": (
            "This ad spent {cost} with minimal results. Estimated savings: {savings}/month."
            " Action: pause this ad. Explain briefly in plain English."
        ),
    },
    RecommendationKind.INCREASE_BUDGET: {
        "pl": (
            "Kampania '{campaign}' osiąga dzienny limit budżetu i ma dobry zwrot z inwestycji"
            " (ROAS: {roas:.1f}x). Sugerowany budżet: {suggested_budget}/dzień (+20%)."
            " Wytłumacz krótko po polsku."
        ),
        "en": (
            "Campaign '{campaign}' is hitting its daily budget limit and has positive ROAS"
            " ({roas:.1f}x). Suggested budget: {suggested_budget}/day (+20%). Explain briefly"
            " in plain English."
        ),
    },
    RecommendationKind.ENABLE_CONVERSION_TRACKING: {
        "pl": (
            "Twoje konto wydaje {cost}/miesiąc na reklamy, ale nie masz skonfigurowanego"
            " śledzenia konwersji (lub tagi są uszkodzone — zero konwersji w ostatnich 7 dniach)."
            " Bez tego nie wiesz, co działa. Wyjaśnij krótko, co należy sprawdzić i naprawić,"
            " po polsku."
        ),
        "en": (
            "Your account is spending {cost}/month on ads but has no working conversion tracking"
            " (conversion actions are enabled but recorded zero conversions in the last 7 days)."
            " Without it you're flying blind. Explain what to check and fix in plain English."
        ),
    },
    RecommendationKind.FIX_DISAPPROVED_AD: {
        "pl": (
            "Reklama ID {ad_id} została odrzucona przez Google i nie wyświetla się. Wymaga"
            " ręcznej poprawki. Wyjaśnij krótko po polsku."
        ),
        "en": (
            "Ad ID {ad_id} has been disapproved by Google and is not showing. It requires"
            " manual review. Explain briefly in plain English."
        ),
    },
    RecommendationKind.CHANGE_MATCH_TYPE: {
        "pl": (
            "Słowo kluczowe '{keyword}' w dopasowaniu szerokim generuje {bleed_pct:.0f}%"
            " ruchu niezwiązanego z Twoją ofertą. Możliwe działanie: zmiana na dopasowanie do"
            " wyrażenia. Wytłumacz krótko po polsku."
        ),
        "en": (
            "Keyword '{keyword}' on broad match is generating {bleed_pct:.0f}% irrelevant"
            " traffic. Action: switch to phrase match. Explain briefly in plain English."
        ),
    },
    RecommendationKind.ADD_AD_VARIATION: {
        "pl": (
            "Grupa reklam '{ad_group}' ma tylko jedną aktywną reklamę i {impressions}"
            " wyświetleń. Dodanie drugiej reklamy pozwoli testować, co lepiej działa."
            " Wytłumacz po polsku."
        ),
        "en": (
            "Ad group '{ad_group}' has only one active ad with {impressions} impressions."
            " Adding a variation enables A/B testing. Explain in plain English."
        ),
    },
    RecommendationKind.ADJUST_BIDDING_STRATEGY: {
        "pl": (
            "Kampania '{campaign}' ma {conversions} konwersji i nadal używa strategii"
            " Maksymalizacja kliknięć. Zmiana na Maksymalizacja konwersji może znacznie"
            " poprawić wyniki. Wytłumacz po polsku."
        ),
        "en": (
            "Campaign '{campaign}' has {conversions} conversions but still uses Maximize"
            " Clicks bidding. Switching to Maximize Conversions could significantly improve"
            " results. Explain in plain English."
        ),
    },
    RecommendationKind.ADJUST_BUDGET: {
        "pl": (
            "Budżet kampanii wymaga korekty. Szacowane oszczędności/zysk: {savings}/miesiąc."
            " Wytłumacz krótko po polsku."
        ),
        "en": (
            "Campaign budget needs adjustment. Estimated savings/gain: {savings}/month."
            " Explain briefly in plain English."
        ),
    },
    RecommendationKind.CTR_DECLINE: {
        "pl": (
            "Współczynnik klikalności (CTR) grupy reklam '{ad_group}' spadł o {ctr_drop_pct:.0f}%"
            " w porównaniu do ubiegłego tygodnia (z {previous_ctr:.2%} do {current_ctr:.2%}),"
            " przy stabilnej liczbie wyświetleń. Oznacza to, że reklamy stają się mniej"
            " atrakcyjne dla użytkowników. Wytłumacz krótko możliwe przyczyny i co zrobić,"
            " po polsku."
        ),
        "en": (
            "Ad group '{ad_group}' CTR dropped {ctr_drop_pct:.0f}% week-over-week"
            " (from {previous_ctr:.2%} to {current_ctr:.2%}) with stable impressions."
            " This means the ads are becoming less compelling to searchers."
            " Explain possible causes and what to review in plain English."
        ),
    },
    RecommendationKind.CPA_SPIKE: {
        "pl": (
            "Koszt pozyskania klienta (CPA) w kampanii '{campaign}' wzrósł o"
            " {cpa_spike_pct:.0f}% w porównaniu do ubiegłego tygodnia. Szacowane dodatkowe"
            " koszty: {savings}/miesiąc. Wytłumacz możliwe przyczyny i działania naprawcze"
            " krótko po polsku."
        ),
        "en": (
            "Campaign '{campaign}' cost-per-conversion spiked {cpa_spike_pct:.0f}%"
            " week-over-week. Estimated extra monthly cost: {savings}."
            " Explain possible causes (bids, competition, landing page) and what to check"
            " in plain English."
        ),
    },
    RecommendationKind.CONVERSION_RATE_DROP: {
        "pl": (
            "Współczynnik konwersji kampanii '{campaign}' spadł o {cvr_drop_pct:.0f}%"
            " w porównaniu do ubiegłego tygodnia (z {previous_cvr:.2%} do {current_cvr:.2%})."
            " Szacowane straty: {savings}/miesiąc. Wytłumacz możliwe przyczyny — np. strona"
            " docelowa, oferta, targeting — po polsku."
        ),
        "en": (
            "Campaign '{campaign}' conversion rate dropped {cvr_drop_pct:.0f}%"
            " week-over-week (from {previous_cvr:.2%} to {current_cvr:.2%})."
            " Estimated lost value: {savings}/month."
            " Explain possible causes — landing page, offer change, audience mismatch —"
            " in plain English."
        ),
    },
    RecommendationKind.IMPRESSION_SHARE_EROSION: {
        "pl": (
            "Udział w wyświetleniach (Impression Share) kampanii '{campaign}' spadł o"
            " {drop_pp:.0%} w ciągu ostatniego tygodnia. Główna przyczyna:"
            " {primary_cause}. Oznacza to, że Twoje reklamy są coraz rzadziej wyświetlane"
            " potencjalnym klientom. Wytłumacz co to znaczy i jak to naprawić, po polsku."
        ),
        "en": (
            "Campaign '{campaign}' search impression share dropped {drop_pp:.0%} this week."
            " Primary cause: {primary_cause}."
            " Your ads are becoming less visible to potential customers."
            " Explain what impression share is and how to recover it in plain English."
        ),
    },
    RecommendationKind.SPEND_ACCELERATION: {
        "pl": (
            "Wydatki kampanii '{campaign}' wzrosły o {spend_growth_pct:.0f}% w porównaniu do"
            " ubiegłego tygodnia, ale liczba konwersji pozostała płaska lub spadła."
            " Szacowane zmarnowane dodatkowe wydatki: {savings}/miesiąc."
            " Wytłumacz dlaczego to niepokojące i co sprawdzić, po polsku."
        ),
        "en": (
            "Campaign '{campaign}' spend grew {spend_growth_pct:.0f}% week-over-week but"
            " conversions stayed flat or declined. Estimated wasted extra spend:"
            " {savings}/month."
            " Explain why this pattern is concerning and what to investigate in plain English."
        ),
    },
    RecommendationKind.QUALITY_SCORE_DETERIORATION: {
        "pl": (
            "Wynik Jakości (Quality Score) słowa kluczowego '{keyword}' spadł z"
            " {previous_quality_score} do {current_quality_score} punktów w ciągu"
            " ostatniego tygodnia. Niższy QS oznacza wyższe koszty kliknięcia i gorsze"
            " pozycje. Szacowane dodatkowe koszty: {savings}/miesiąc."
            " Wytłumacz co mogło spowodować spadek i jak to naprawić, po polsku."
        ),
        "en": (
            "Keyword '{keyword}' Quality Score dropped from {previous_quality_score} to"
            " {current_quality_score} this week. Lower QS means higher CPCs and worse"
            " ad positions. Estimated extra monthly cost: {savings}."
            " Explain what could have caused the drop (ad relevance, landing page, CTR)"
            " and how to fix it in plain English."
        ),
    },
    RecommendationKind.AD_KEYWORD_MISMATCH: {
        "pl": (
            "Reklama (ID {ad_id}) w grupie {ad_group_id} ma niskie dopasowanie treści do"
            " słów kluczowych — tylko {coverage_pct:.0f}% tokenów słów kluczowych pojawia się"
            " w nagłówkach reklamy. Google nagradza wyższe dopasowanie słów kluczowych do"
            " reklamy lepszym Wynikiem Jakości i niższymi kosztami kliknięcia."
            " Wytłumacz co to znaczy i jak poprawić nagłówki, po polsku."
        ),
        "en": (
            "Ad (ID {ad_id}) in ad group {ad_group_id} has low keyword-to-ad relevance —"
            " only {coverage_pct:.0f}% of keyword tokens appear in the ad headlines."
            " Google rewards higher keyword-ad alignment with better Quality Score and"
            " lower CPCs. Explain what this means and how to improve the headlines"
            " in plain English."
        ),
    },
    RecommendationKind.MISSING_CTA: {
        "pl": (
            "Reklama (ID {ad_id}) nie zawiera żadnego wezwania do działania (CTA) w"
            " {headline_count} nagłówkach ani opisach. Reklamy bez CTA mają niższy"
            " współczynnik klikalności i konwersji — użytkownicy muszą wiedzieć, co mają"
            " zrobić. Wytłumacz jak dodać skuteczne CTA, po polsku."
        ),
        "en": (
            "Ad (ID {ad_id}) has no call-to-action in any of its {headline_count} headlines"
            " or descriptions. Ads without a CTA get lower CTR and conversion rates —"
            " users need to be told what to do next."
            " Explain how to add an effective CTA in plain English."
        ),
    },
    RecommendationKind.WEAK_RSA_STRENGTH: {
        "pl": (
            "Responsywna reklama (ID {ad_id}) ma słabą ocenę jakości Google: {reason}."
            " Niski Ad Strength oznacza mniej wyświetleń i gorsze wyniki algorytmu"
            " optymalizacji. Google zaleca minimum 8 unikalnych nagłówków."
            " Wytłumacz jak poprawić jakość reklamy, po polsku."
        ),
        "en": (
            "Responsive search ad (ID {ad_id}) has weak Google ad strength: {reason}."
            " Low Ad Strength means fewer impressions and worse algorithm optimisation."
            " Google recommends at least 8 unique headlines."
            " Explain how to improve ad strength in plain English."
        ),
    },
    RecommendationKind.AD_FATIGUE: {
        "pl": (
            "Reklama (ID {ad_id}) wykazuje oznaki zmęczenia — CTR spadł o"
            " {ctr_drop_pct:.0f}% w porównaniu do ubiegłego tygodnia (z {previous_ctr:.2%}"
            " do {current_ctr:.2%}), przy stabilnej liczbie wyświetleń."
            " Użytkownicy coraz częściej ignorują tę samą treść reklamy."
            " Wytłumacz co to znaczy i jak odświeżyć kreację, po polsku."
        ),
        "en": (
            "Ad (ID {ad_id}) shows signs of fatigue — CTR dropped {ctr_drop_pct:.0f}%"
            " week-over-week (from {previous_ctr:.2%} to {current_ctr:.2%})"
            " with stable impression volume."
            " Users are increasingly scrolling past the same creative."
            " Explain what ad fatigue is and how to refresh the copy in plain English."
        ),
    },
    RecommendationKind.REDUNDANT_HEADLINES: {
        "pl": (
            "Responsywna reklama (ID {ad_id}) ma {redundant_headline_count} z"
            " {total_headlines} nagłówków, które brzmią niemal identycznie."
            " Algorytm Google ma wtedy mniej różnorodnych kombinacji do testowania,"
            " co ogranicza naukę i osłabia wyniki. Każdy nagłówek powinien przekazywać"
            " inny argument. Wytłumacz jak to poprawić, po polsku."
        ),
        "en": (
            "Responsive search ad (ID {ad_id}) has {redundant_headline_count} out of"
            " {total_headlines} headlines that say nearly the same thing."
            " Google's algorithm has fewer unique combinations to test, limiting"
            " learning and hurting ad strength."
            " Each headline should communicate a different selling point."
            " Explain how to diversify them in plain English."
        ),
    },
    RecommendationKind.OVERSTUFFED_AD_GROUP: {
        "pl": (
            "Grupa reklam '{ad_group_name}' zawiera {enabled_keywords} aktywnych słów"
            " kluczowych, co znacznie przekracza zalecany limit {threshold}."
            " Zbyt wiele słów kluczowych w jednej grupie obniża trafność reklam i Wynik"
            " Jakości — Google nie może dobrze dopasować reklamy do każdego zapytania."
            " Wytłumacz jak reorganizować grupy reklam po tematach, po polsku."
        ),
        "en": (
            "Ad group '{ad_group_name}' has {enabled_keywords} active keywords,"
            " far exceeding the recommended limit of {threshold}."
            " Too many keywords in one group reduces ad relevance and Quality Score —"
            " Google can't match the ad well to every query."
            " Explain how to reorganise ad groups by tightly themed topics in plain English."
        ),
    },
    RecommendationKind.KEYWORD_CANNIBALIZATION: {
        "pl": (
            "Słowo kluczowe '{keyword_text}' jest aktywne w {duplicate_count} różnych"
            " grupach reklam jednocześnie, w tym w '{ad_group_name}'."
            " To powoduje, że kampanie konkurują ze sobą w aukcjach, podnosząc koszty i"
            " rozkładając dane o efektywności. Google nie wie, którą reklamę pokazać."
            " Wytłumacz czym jest kanibalizacja słów kluczowych i jak to naprawić, po polsku."
        ),
        "en": (
            "Keyword '{keyword_text}' is active in {duplicate_count} different ad groups"
            " simultaneously, including '{ad_group_name}'."
            " This makes your own campaigns compete against each other in auctions,"
            " inflating costs and splitting performance data. Google doesn't know which"
            " ad to show."
            " Explain what keyword cannibalization is and how to fix it in plain English."
        ),
    },
    RecommendationKind.NEGATIVE_KEYWORD_CONFLICT: {
        "pl": (
            "Słowo wykluczające '{negative_text}' ({negative_match_type}) blokuje aktywne"
            " słowo kluczowe '{keyword_text}' na poziomie {conflict_scope}."
            " Oznacza to, że Twoja reklama nigdy się nie wyświetli na to słowo kluczowe,"
            " choć za nie płacisz. To jeden z najpoważniejszych błędów strukturalnych"
            " w Google Ads. Wytłumacz jak zidentyfikować i usunąć konflikt, po polsku."
        ),
        "en": (
            "Negative keyword '{negative_text}' ({negative_match_type}) is blocking active"
            " keyword '{keyword_text}' at the {conflict_scope} level."
            " This means your ad will never show for this keyword despite it being active."
            " This is one of the most damaging structural mistakes in Google Ads."
            " Explain how to identify and resolve the conflict in plain English."
        ),
    },
    RecommendationKind.ORPHANED_CAMPAIGN: {
        "pl": (
            "Kampania '{campaign_name}' jest aktywna z budżetem {budget_micros} mikro,"
            " ale nie ma żadnych aktywnych grup reklam ({ad_group_count} grup, wszystkie"
            " wstrzymane lub usunięte). Budżet jest codziennie rezerwowany, ale żadna"
            " reklama się nie wyświetla. Szacowane oszczędności: {savings}/miesiąc."
            " Wytłumacz co zrobić z tą kampanią, po polsku."
        ),
        "en": (
            "Campaign '{campaign_name}' is active with a budget of {budget_micros} micros"
            " but has no active ad groups ({ad_group_count} groups, all paused or removed)."
            " Budget is being reserved daily but no ads are showing."
            " Estimated savings: {savings}/month."
            " Explain what to do with this campaign in plain English."
        ),
    },
    RecommendationKind.MATCH_TYPE_REDUNDANCY: {
        "pl": (
            "Słowo kluczowe '{keyword_text}' w grupie reklam '{ad_group_name}' istnieje"
            " jednocześnie w dopasowaniu szerokim i bardziej precyzyjnym"
            " ({match_types})."
            " Dopasowanie szerokie jest zbędne, gdy istnieje już dokładne lub do wyrażenia"
            " — Google i tak obsłuży te zapytania, a szerokie może generować nieistotny"
            " ruch. Wytłumacz dlaczego to problem i co zrobić, po polsku."
        ),
        "en": (
            "Keyword '{keyword_text}' in ad group '{ad_group_name}' exists simultaneously"
            " as broad match and a more specific match type ({match_types})."
            " Broad match is redundant when exact or phrase already exists —"
            " Google will serve the specific match types anyway, while broad may attract"
            " irrelevant traffic."
            " Explain why this is a problem and what to do in plain English."
        ),
    },
    RecommendationKind.GENERIC_DESCRIPTION: {
        "pl": (
            "Wszystkie opisy reklamy (ID {ad_id}) są zbyt ogólne — nie zawierają żadnych"
            " liczb, cen, procentów ani konkretnych korzyści."
            " Treści takie jak 'Wysokiej jakości usługi' brzmią jak każda inna reklama."
            " Konkretne dane ('Oszczędź 30%', 'Od 49 zł/mies.') budują zaufanie i"
            " zwiększają klikalność. Wytłumacz jak dodać konkrety, po polsku."
        ),
        "en": (
            "All descriptions in ad (ID {ad_id}) are generic — they contain no numbers,"
            " prices, percentages, or specific claims."
            " Copy like 'High quality service' sounds like every other ad."
            " Specifics like 'Save 30%' or 'From €49/month' build trust and boost CTR."
            " Explain how to make the descriptions more concrete in plain English."
        ),
    },
    # ── Module 4 — Audience & Targeting Intelligence ──────────────────────────
    RecommendationKind.DEVICE_BID_ADJUSTMENT: {
        "pl": (
            "W kampanii '{campaign_name}' koszt konwersji na urządzeniach mobilnych"
            " ({mobile_cpa_micros} mikro) jest {ratio}× wyższy niż na komputerach"
            " ({desktop_cpa_micros} mikro) przy {desktop_conversions} konwersjach."
            " Obniżenie stawki dla mobile zredukuje wydatki bez utraty wartościowych"
            " konwersji. Wytłumacz jak dodać korektę stawek dla urządzeń, po polsku."
        ),
        "en": (
            "In campaign '{campaign_name}', mobile CPA ({mobile_cpa_micros} micros) is"
            " {ratio}× higher than desktop ({desktop_cpa_micros} micros) across"
            " {desktop_conversions} desktop conversions."
            " Adding a negative mobile bid adjustment will cut wasted spend without"
            " losing high-value conversions."
            " Explain how to set a device bid adjustment in plain English."
        ),
    },
    RecommendationKind.GEO_EXCLUSION: {
        "pl": (
            "Lokalizacja o ID '{location_id}' w kampanii '{campaign_name}' kosztowała"
            " {cost_micros} mikro przy {clicks} kliknięciach i 0 konwersjach przez"
            " ostatnie 30 dni. Wykluczenie tej lokalizacji zatrzyma marnowanie budżetu."
            " Szacowane oszczędności: {savings_micros} mikro."
            " Wytłumacz jak wykluczyć lokalizację w kampanii, po polsku."
        ),
        "en": (
            "Location '{location_id}' in campaign '{campaign_name}' spent"
            " {cost_micros} micros across {clicks} clicks with 0 conversions over 30 days."
            " Excluding this location will stop budget waste immediately."
            " Estimated savings: {savings_micros} micros."
            " Explain how to exclude a location in plain English."
        ),
    },
    RecommendationKind.AD_SCHEDULE_ADJUSTMENT: {
        "pl": (
            "Kampania '{campaign_name}' wydała {cost_micros} mikro w godzinie"
            " {hour_of_day}:00–{hour_of_day}:59 przy 0 konwersjach przez ostatnie"
            " 30 dni. Ustawienie korekty stawki −100% dla tej godziny zatrzyma"
            " wyświetlanie reklam w czasie, który nie przynosi wyników."
            " Wytłumacz jak ustawić harmonogram reklam, po polsku."
        ),
        "en": (
            "Campaign '{campaign_name}' spent {cost_micros} micros during hour"
            " {hour_of_day}:00–{hour_of_day}:59 with 0 conversions over 30 days."
            " Setting a −100% bid adjustment for that hour will stop showing ads"
            " at a time that never converts."
            " Explain how to set an ad schedule in plain English."
        ),
    },
    RecommendationKind.DAY_OF_WEEK_BID_ADJUSTMENT: {
        "pl": (
            "W kampanii '{campaign_name}' dzień '{day_of_week}' ma CPA {day_cpa_micros}"
            " mikro — {ratio}× powyżej średniej konta ({account_avg_cpa_micros} mikro)"
            " przy {conversions} konwersjach."
            " Obniżenie stawek w ten dzień poprawi efektywność budżetu."
            " Wytłumacz jak ustawić korektę stawek dla dnia tygodnia, po polsku."
        ),
        "en": (
            "In campaign '{campaign_name}', '{day_of_week}' has a CPA of"
            " {day_cpa_micros} micros — {ratio}× above the account average"
            " ({account_avg_cpa_micros} micros) across {conversions} conversions."
            " Reducing bids on this day will improve budget efficiency."
            " Explain how to set a day-of-week bid adjustment in plain English."
        ),
    },
    # ── Module 5 — Budget & Bidding Strategy ──────────────────────────────────
    RecommendationKind.REALLOCATE_BUDGET: {
        "pl": (
            "Kampania '{receiver_campaign_name}' ma ROAS {receiver_roas} i wykorzystuje"
            " {receiver_budget_utilisation:.0%} budżetu (ograniczona budżetem),"
            " podczas gdy kampania '{donor_campaign_name}' ma ROAS {donor_roas}"
            " i wydaje tylko {donor_budget_utilisation:.0%} budżetu."
            " Przeniesienie budżetu z gorzej działającej kampanii do lepszej poprawi"
            " łączny zwrot z inwestycji konta."
            " Sezonowy mnożnik dla tej branży wynosi {seasonal_multiplier}×"
            " (wyższe wartości oznaczają szczyt sezonu, niższe — poza sezonem)."
            " Wytłumacz jak zmienić budżety kampanii, po polsku."
        ),
        "en": (
            "Campaign '{receiver_campaign_name}' has a ROAS of {receiver_roas} but is"
            " budget-constrained at {receiver_budget_utilisation:.0%} utilisation,"
            " while '{donor_campaign_name}' has a ROAS of {donor_roas} and only"
            " spends {donor_budget_utilisation:.0%} of its budget."
            " Moving budget from the under-performer to the top performer will improve"
            " the account's overall return."
            " The seasonal demand multiplier for this vertical is {seasonal_multiplier}×"
            " (above 1.0 = peak season, below 1.0 = off season)."
            " Explain how to reallocate campaign budgets in plain English."
        ),
    },
    RecommendationKind.IMPROVE_QUALITY_SCORE: {
        "pl": (
            "Kampania '{campaign_name}' traci {search_rank_lost_impression_share:.0%}"
            " wyświetleń z powodu niskiego Ad Rank (jakość reklamy i strony docelowej)."
            " Poprawa trafności reklamy, oczekiwanego CTR i jakości strony docelowej"
            " zwiększy Ad Rank bez podwyżki stawek."
            " Wytłumacz jak poprawić wynik jakości (Quality Score), po polsku."
        ),
        "en": (
            "Campaign '{campaign_name}' is losing {search_rank_lost_impression_share:.0%}"
            " of eligible impressions due to low Ad Rank (ad quality and landing-page"
            " experience)."
            " Improving ad relevance, expected CTR, and landing-page quality raises"
            " Ad Rank without increasing bids."
            " Explain how to improve Quality Score in plain English."
        ),
    },
    RecommendationKind.RELAX_TARGET_CPA: {
        "pl": (
            "Kampania '{campaign_name}' używa strategii TARGET_CPA z celem"
            " {target_cpa_micros} mikro — to tylko {ratio:.0%} średniego CPA konta"
            " ({account_avg_cpa_micros} mikro). Tak agresywny cel ogranicza udział"
            " w aukcjach i powoduje niski wolumen ({conversions} konwersji)."
            " Sugerowany cel: {suggested_target_cpa_micros} mikro (75% średniej konta)."
            " Wytłumacz dlaczego zbyt niski target CPA blokuje wzrost, po polsku."
        ),
        "en": (
            "Campaign '{campaign_name}' uses TARGET_CPA with a target of"
            " {target_cpa_micros} micros — only {ratio:.0%} of the account average"
            " ({account_avg_cpa_micros} micros). This aggressive target restricts auction"
            " participation and results in low volume ({conversions} conversions)."
            " Suggested target: {suggested_target_cpa_micros} micros (75% of account avg)."
            " Explain why an overly tight Target CPA limits growth in plain English."
        ),
    },
    RecommendationKind.DIVERSIFY_CHANNELS: {
        "pl": (
            "Kampania '{campaign_name}' zwiększyła wydatki o {cost_growth_pct}% w ciągu"
            " tygodnia, ale liczba konwersji wzrosła tylko o {conv_growth_pct}%."
            " To znak malejących zwrotów — wyszukiwania w tej kampanii są już w dużej"
            " mierze wyczerpane. Rozważ przeniesienie przyrostowego budżetu na inne"
            " kanały (Display, YouTube, Performance Max)."
            " Wytłumacz koncepcję malejących zwrotów i dywersyfikacji kanałów, po polsku."
        ),
        "en": (
            "Campaign '{campaign_name}' increased spend by {cost_growth_pct}% week-over-week"
            " but conversions grew by only {conv_growth_pct}%."
            " This is a sign of diminishing returns — available search demand is largely"
            " saturated. Consider allocating incremental budget to other channels"
            " (Display, YouTube, Performance Max)."
            " Explain diminishing returns and channel diversification in plain English."
        ),
    },
    # ── Module 6 — Conversion Tracking & Measurement ──────────────────────────
    RecommendationKind.UPGRADE_CONVERSION_ACTION: {
        "pl": (
            "Konto śledzi tylko mikro-konwersje ({micro_conversion_count} akcji:"
            " {micro_conversion_names}). Takie zdarzenia jak odsłony stron czy kliknięcia"
            " nie odzwierciedlają rzeczywistych wyników biznesowych. Smart Bidding"
            " optymalizuje pod kątem tych sygnałów, co prowadzi do gromadzenia ruchu bez"
            " realnych zakupów ani leadów. Wytłumacz jak skonfigurować konwersje oparte"
            " na zakupach lub leadach, po polsku."
        ),
        "en": (
            "This account only tracks micro-conversions ({micro_conversion_count} actions:"
            " {micro_conversion_names}). Events like page views and clicks don't reflect"
            " real business outcomes. Smart Bidding optimises for these signals, collecting"
            " traffic without real purchases or leads."
            " Explain how to set up purchase or lead-based conversions in plain English."
        ),
    },
    RecommendationKind.DEDUPLICATE_CONVERSIONS: {
        "pl": (
            "Wskaźnik 'Wszystkie konwersje' ({total_all_conversions:.0f}) jest"
            " {ratio:.1f}× wyższy niż 'Konwersje' ({total_conversions:.0f}). Tak duża"
            " różnica wskazuje na podwójne liczenie — prawdopodobnie tag Google i"
            " importowany cel z GA4 rejestrują tę samą akcję. Zawyżone dane konwersji"
            " zniekształcają optymalizację bidowania i raportowanie ROI."
            " Wytłumacz jak zidentyfikować i naprawić podwójne liczenie, po polsku."
        ),
        "en": (
            "'All conversions' ({total_all_conversions:.0f}) is {ratio:.1f}× higher than"
            " 'Conversions' ({total_conversions:.0f}). Such a large gap typically means"
            " double-counting — a Google tag and an imported GA4 goal are tracking the"
            " same event. Inflated conversion data distorts Smart Bidding and ROI reporting."
            " Explain how to identify and fix conversion deduplication in plain English."
        ),
    },
    RecommendationKind.SET_CONVERSION_VALUE: {
        "pl": (
            "Konto ma {total_conversions:.0f} konwersji, ale wartość konwersji wynosi 0."
            " Bez wartości konwersji Google nie może optymalizować pod kątem ROAS, a"
            " właściciel konta nie może obliczyć rzeczywistego zwrotu z inwestycji."
            " Dodaj wartości do akcji konwersji lub użyj dynamicznych wartości konwersji."
            " Wytłumacz jak ustawić wartości konwersji, po polsku."
        ),
        "en": (
            "This account has {total_conversions:.0f} conversions but a conversion value"
            " of zero. Without conversion values Google cannot optimise for ROAS, and you"
            " cannot calculate your true return on ad spend."
            " Add static values to your conversion actions or implement dynamic conversion"
            " values. Explain how to set conversion values in plain English."
        ),
    },
    RecommendationKind.ADD_AUDIENCE_SIGNALS: {
        "pl": (
            "Kampania '{campaign_name}' ma {impressions} wyświetleń, ale nie ma"
            " żadnych list odbiorców w trybie obserwacji."
            " Dodanie odbiorców pozwoli algorytmowi Google lepiej dostosować stawki"
            " do profilu konwertujących użytkowników i poprawić ROI."
            " Wytłumacz jak dodać listy odbiorców w trybie obserwacji, po polsku."
        ),
        "en": (
            "Campaign '{campaign_name}' has {impressions} impressions but no audience"
            " lists attached in observation mode."
            " Adding audiences lets Google's bidding algorithm learn who converts best"
            " and improve your ROI over time."
            " Explain how to add observation audiences in plain English."
        ),
    },
    RecommendationKind.ADD_SITELINKS: {
        "pl": (
            "Kampania '{campaign_name}' ma {impressions} wyświetleń, ale nie ma"
            " żadnych rozszerzeń sitelink."
            " Sitelinki zwiększają powierzchnię reklamy, poprawiają CTR i jakość reklamy"
            " bez dodatkowych kosztów."
            " Wytłumacz jak dodać rozszerzenia sitelink do kampanii, po polsku."
        ),
        "en": (
            "Campaign '{campaign_name}' has {impressions} impressions but no sitelink"
            " extensions attached."
            " Sitelinks expand your ad's real estate, improve CTR, and boost Ad Rank at"
            " no extra cost."
            " Explain how to add sitelink extensions in plain English."
        ),
    },
    RecommendationKind.ADD_CALLOUTS: {
        "pl": (
            "Kampania '{campaign_name}' ma {impressions} wyświetleń, ale nie ma"
            " rozszerzeń callout."
            " Callout extensions wyświetlają krótkie frazy o zaletach oferty pod treścią"
            " reklamy, zwiększając CTR i jakość reklamy."
            " Wytłumacz jak dodać rozszerzenia callout, po polsku."
        ),
        "en": (
            "Campaign '{campaign_name}' has {impressions} impressions but no callout"
            " extensions attached."
            " Callout extensions display short benefit phrases below the ad text,"
            " improving CTR and Ad Rank at zero extra cost."
            " Explain how to add callout extensions in plain English."
        ),
    },
    RecommendationKind.ADD_STRUCTURED_SNIPPETS: {
        "pl": (
            "Kampania '{campaign_name}' ma {impressions} wyświetleń, ale nie ma"
            " rozszerzeń structured snippet."
            " Rozszerzenia te prezentują listę cech produktów lub usług, zwiększając"
            " trafność reklamy i współczynnik klikalności."
            " Wytłumacz jak dodać structured snippets do kampanii, po polsku."
        ),
        "en": (
            "Campaign '{campaign_name}' has {impressions} impressions but no structured"
            " snippet extensions attached."
            " Structured snippets highlight specific product or service features,"
            " boosting ad relevance and CTR."
            " Explain how to add structured snippet extensions in plain English."
        ),
    },
    RecommendationKind.REFRESH_SITELINK: {
        "pl": (
            "Sitelink (asset_id={asset_id}) w kampanii (campaign_id={campaign_id})"
            " miał {impressions} wyświetleń przez ostatnie 30 dni, ale CTR wynosi"
            " tylko {ctr_pct:.2f}% — poniżej progu 0.5%."
            " Treść lub strona docelowa tego sitelinku nie angażuje użytkowników."
            " Wytłumacz jak odświeżyć lub zastąpić ten sitelink, po polsku."
        ),
        "en": (
            "Sitelink (asset_id={asset_id}) in campaign (campaign_id={campaign_id})"
            " received {impressions} impressions over the past 30 days but has a CTR"
            " of only {ctr_pct:.2f}% — below the 0.5% threshold."
            " The sitelink copy or landing page is not resonating with users."
            " Explain how to refresh or replace this sitelink in plain English."
        ),
    },
    RecommendationKind.PROMOTE_SEARCH_TERM: {
        "pl": (
            'Fraza wyszukiwania "{search_term}" wygenerowała {conversions:.0f} konwersji'
            " przy CPA {cpa_pln:.2f} zł (średnia konta: {avg_cpa_pln:.2f} zł),"
            " ale nie jest jeszcze dodana jako słowo kluczowe."
            " Dodanie jej jako dopasowanie ścisłe [exact] w grupie reklam {ad_group_id}"
            " pozwoli precyzyjnie zarządzać stawkami i tekstami reklam."
            " Wytłumacz korzyści z promowania tej frazy, po polsku."
        ),
        "en": (
            'Search term "{search_term}" generated {conversions:.0f} conversions'
            " at a CPA of {cpa_pln:.2f} PLN (account average: {avg_cpa_pln:.2f} PLN)"
            " but is not yet added as a keyword."
            " Adding it as an exact-match keyword in ad group {ad_group_id}"
            " will let you control bids and ad copy for this high-value query."
            " Explain the benefit of promoting this search term in plain English."
        ),
    },
    RecommendationKind.ABOVE_VERTICAL_BENCHMARK: {
        "pl": (
            "Twoje konto ma CPA {account_cpa_pln:.2f} zł, czyli o {pct_above_p75:.1f}%"
            " powyżej górnego kwartyla (p75 = {benchmark_p75_pln:.2f} zł)"
            ' dla branży "{vertical}" (tier {city_tier}).'
            " Mediana benchmarku to {benchmark_median_pln:.2f} zł"
            " na podstawie {benchmark_account_count} kont."
            " Wskaż konkretne obszary kampanii do optymalizacji CPA, po polsku."
        ),
        "en": (
            "Your account CPA is {account_cpa_pln:.2f} PLN — {pct_above_p75:.1f}%"
            " above the vertical p75 benchmark ({benchmark_p75_pln:.2f} PLN)"
            ' for the "{vertical}" vertical (city tier {city_tier}).'
            " The benchmark median is {benchmark_median_pln:.2f} PLN"
            " across {benchmark_account_count} accounts."
            " Suggest specific campaign optimisations to bring CPA closer to benchmark."
        ),
    },
}


def format_micros_as_currency(micros: int, currency: str = "EUR") -> str:
    """Convert micros to human-readable currency string.

    Examples:
        10_500_000 -> '€10.50'
        1_000_000_000 -> '€1000.00'
        PLN: 1_234_560_000 -> '1 234,56 zł'
    """
    if currency == "PLN":
        from adcopilot.domain.polish_market.currency import format_pln_micros

        return format_pln_micros(micros)
    symbols = {"EUR": "€", "USD": "$", "GBP": "£"}
    symbol = symbols.get(currency, currency + " ")
    value = micros / 1_000_000
    return f"{symbol}{value:.2f}"
