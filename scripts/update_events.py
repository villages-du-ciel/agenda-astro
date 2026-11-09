#!/usr/bin/env python3
"""Importe les maxima de pluies de météores depuis le calendrier IMO."""
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

SOURCE = "https://www.imo.net/calendar/"
DATA_FILE = Path("data/evenements.json")
MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
NAMES = {
    "Leonids": "Léonides",
    "Geminids": "Géminides",
    "Ursids": "Ursides",
    "Quadrantids": "Quadrantides",
    "Lyrids": "Lyrides",
    "Eta Aquariids": "Êta Aquarides",
    "Perseids": "Perséides",
    "Southern Delta Aquariids": "Delta Aquarides du Sud",
    "Alpha Capricornids": "Alpha Capricornides",
    "Orionids": "Orionides",
    "Southern Taurids": "Taurides du Sud",
    "Northern Taurids": "Taurides du Nord",
}


def fetch_text():
    request = Request(
        SOURCE,
        headers={"User-Agent": "AstroClubAgenda/1.2 (astronomy calendar updater)"},
    )
    with urlopen(request, timeout=30) as response:
        soup = BeautifulSoup(response.read(), "html.parser")
    return " ".join(soup.get_text(" ", strip=True).split())


def extract_peak_date(segment, today):
    peak = re.search(r"PEAK\s*NIGHT\s*:?\s*(.{0,100})", segment, re.IGNORECASE)
    if not peak:
        return None

    # Formats pris en charge : "Nov 17/18", "Nov 17–18", "17 Nov", "17–18 Nov".
    text = peak.group(1)
    patterns = [
        r"\b([A-Za-z]{3})\s+(\d{1,2})(?:\s*[/–-]\s*\d{1,2})?",
        r"\b(\d{1,2})(?:\s*[/–-]\s*\d{1,2})?\s+([A-Za-z]{3})\b",
    ]
    parsed = None
    for index, pattern in enumerate(patterns):
        match = re.search(pattern, text)
        if not match:
            continue
        month_text, day_text = (match.group(1), match.group(2)) if index == 0 else (match.group(2), match.group(1))
        month = MONTHS.get(month_text.lower())
        if month:
            parsed = (int(day_text), month)
            break
    if parsed is None:
        return None

    day, month = parsed
    year = today.year if month >= today.month else today.year + 1
    try:
        result = date(year, month, day)
    except ValueError:
        return None
    return result if result >= today else None


def build_events(page_text, today):
    # Cherche les noms dans le texte complet, pas dans des balises HTML précises :
    # le site IMO peut modifier sa mise en page sans casser l'import.
    occurrences = []
    for english_name in sorted(NAMES, key=len, reverse=True):
        for match in re.finditer(r"\b" + re.escape(english_name) + r"\b", page_text, re.IGNORECASE):
            occurrences.append((match.start(), match.end(), english_name))
    occurrences.sort()

    generated = []
    seen = set()
    for position, (start, end, english_name) in enumerate(occurrences):
        next_start = occurrences[position + 1][0] if position + 1 < len(occurrences) else min(len(page_text), end + 1200)
        # Une même pluie peut être mentionnée plusieurs fois : on ne retient que
        # le segment où se trouve effectivement l'indication « Peak night ».
        segment = page_text[start:next_start]
        peak_date = extract_peak_date(segment, today)
        if peak_date is None:
            continue

        french_name = NAMES[english_name]
        title = "Maximum des " + french_name
        key = (title, peak_date.isoformat())
        if key in seen:
            continue
        seen.add(key)

        generated.append({
            "date": peak_date.isoformat(),
            "endDate": None,
            "title": title,
            "category": "Pluie d’étoiles filantes",
            "scope": "france",
            "visibility": "Observable selon la hauteur du radiant, l’horizon, la Lune et la météo ; conditions locales à vérifier depuis Les Herbiers.",
            "summary": f"Maximum annoncé par l’International Meteor Organization pour les {french_name}. L’activité réellement observée dépend des conditions du ciel.",
            "details": "Consulter le calendrier IMO pour la période d’activité et les particularités de cette pluie.",
            "time": "Nuit du maximum ; heure précise à vérifier dans le calendrier IMO.",
            "where": "Observer une large portion du ciel depuis un endroit sombre.",
            "direction": "Direction et hauteur du radiant à vérifier pour l’heure d’observation depuis Les Herbiers.",
            "altitude": "Non calculée automatiquement.",
            "moon": "Conditions lunaires à vérifier dans le calendrier IMO.",
            "weather": "Vérifier les prévisions près des Herbiers le jour même.",
            "equipment": "Observation à l’œil nu ; aucun instrument nécessaire.",
            "tips": "S’éloigner des éclairages et laisser les yeux s’adapter à l’obscurité.",
            "source": SOURCE,
        })

    return sorted(generated, key=lambda event: event["date"])


def main():
    if not DATA_FILE.exists():
        raise SystemExit(f"Fichier introuvable : {DATA_FILE}")
    with DATA_FILE.open(encoding="utf-8") as stream:
        current = json.load(stream)
    if not isinstance(current, list):
        raise SystemExit("Le fichier JSON doit contenir une liste d'événements.")

    page_text = fetch_text()
    generated = build_events(page_text, date.today())
    if len(generated) < 4:
        raise SystemExit(
            f"Seulement {len(generated)} maxima futurs reconnus dans la page IMO ; "
            "aucune modification effectuée. Vérifier la structure de la source."
        )

    generated_titles = {event["title"] for event in generated}
    other_events = [
        event for event in current
        if event.get("category") != "Pluie d’étoiles filantes"
        and event.get("title") not in generated_titles
    ]
    merged = other_events + generated
    merged.sort(key=lambda event: event.get("date", "9999-12-31"))
    DATA_FILE.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"OK : {len(generated)} maxima importés depuis l'IMO ; "
        f"{len(other_events)} autres événements conservés."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Échec de l'actualisation : {error}", file=sys.stderr)
        raise
