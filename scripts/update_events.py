#!/usr/bin/env python3
"""Actualise les pluies de météores depuis le calendrier officiel de l'IMO.

Le script ne remplace que les fiches de catégorie « Pluie d’étoiles filantes ».
Si la page source change ou si les dates ne sont pas reconnues, il s'arrête
sans toucher au fichier JSON.
"""
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
FRENCH_NAMES = {
    "Leonids": "Léonides", "Geminids": "Géminides", "Ursids": "Ursides",
    "Quadrantids": "Quadrantides", "Lyrids": "Lyrides",
    "Eta Aquariids": "Êta Aquarides", "Perseids": "Perséides",
    "Southern Delta Aquariids": "Delta Aquarides du Sud",
    "Alpha Capricornids": "Alpha Capricornides",
    "Orionids": "Orionides", "Southern Taurids": "Taurides du Sud",
    "Northern Taurids": "Taurides du Nord",
}
HEADERS = {"User-Agent": "AstroClubAgenda/1.0 (public astronomy calendar updater)"}


def fetch_page():
    req = Request(SOURCE, headers=HEADERS)
    with urlopen(req, timeout=30) as response:
        return BeautifulSoup(response.read(), "html.parser")


def find_card_text(heading):
    node = heading
    for _ in range(6):
        if node is None:
            break
        text = " ".join(node.get_text(" ", strip=True).split())
        if "PEAK NIGHT" in text.upper() and re.search(
            r"\b\d{1,2}\s*[–-]\s*\d{1,2}\s+[A-Za-z]{3}\b", text
        ):
            return text
        node = node.parent
    return ""


def parse_peak(text, today):
    match = re.search(
        r"PEAK NIGHT\s+(\d{1,2})\s*[–-]\s*(\d{1,2})\s+([A-Za-z]{3})",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    day = int(match.group(1))
    month_name = match.group(3).lower()
    month = MONTHS.get(month_name)
    if not month:
        return None
    years = [today.year, today.year + 1, today.year + 2]
    candidates = []
    for year in years:
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if candidate >= today:
            candidates.append(candidate)
    return min(candidates) if candidates else None


def build_events(soup, today):
    generated = []
    for heading in soup.find_all(["h2", "h3"]):
        english_name = heading.get_text(" ", strip=True)
        if english_name not in FRENCH_NAMES:
            continue
        text = find_card_text(heading)
        if not text:
            continue
        peak = parse_peak(text, today)
        if peak is None:
            continue

        name = FRENCH_NAMES[english_name]
        title = "Maximum des " + name
        # Keep a concise source description, without copying the full IMO article.
        description = ""
        active = re.search(r"Active through\s+(.+?)(?:\s+[A-Z][a-z].*|$)", text)
        moon = re.search(
            r"(The Moon will be .{0,140}?)(?:\.| Expect | Generally | Very )",
            text,
            flags=re.IGNORECASE,
        )
        if active:
            description = "Période d’activité indiquée par l’IMO : " + active.group(1).strip()
        moon_text = moon.group(1).strip() if moon else (
            "Éclairage lunaire : consulter le calendrier IMO avant l’observation."
        )

        generated.append({
            "date": peak.isoformat(),
            "endDate": None,
            "title": title,
            "category": "Pluie d’étoiles filantes",
            "scope": "france",
            "visibility": "Observable selon la hauteur du radiant, l’horizon et la météo ; conditions locales à vérifier depuis Les Herbiers.",
            "summary": f"Maximum annoncé pour les {name}. L’activité réelle varie ; le nombre de météores observés dépend du ciel et de la pollution lumineuse.",
            "details": description or "Consulter la fiche IMO pour la période d’activité et les particularités de cette pluie.",
            "time": "Nuit du maximum indiquée par l’IMO ; heure précise à consulter dans le calendrier source.",
            "where": "Observer une large portion du ciel ; ne pas fixer uniquement le radiant.",
            "direction": "À déterminer selon la hauteur du radiant depuis Les Herbiers et l’heure d’observation.",
            "altitude": "Non calculée automatiquement dans cette fiche.",
            "moon": moon_text,
            "weather": "Vérifier les nuages et la transparence du ciel près des Herbiers le jour même.",
            "equipment": "Œil nu ; jumelles et télescope non nécessaires pour observer les météores.",
            "tips": "S’éloigner des éclairages, laisser les yeux s’adapter à l’obscurité et prévoir des vêtements adaptés.",
            "source": SOURCE,
        })
    # Avoid duplicates and keep the nearest occurrence of each shower.
    unique = {}
    for event in generated:
        unique[(event["title"], event["date"])] = event
    return sorted(unique.values(), key=lambda event: event["date"])


def main():
    today = date.today()
    if not DATA_FILE.exists():
        raise SystemExit(f"Fichier introuvable : {DATA_FILE}")
    with DATA_FILE.open(encoding="utf-8") as stream:
        current = json.load(stream)
    if not isinstance(current, list):
        raise SystemExit("Le fichier d'événements doit contenir une liste JSON.")

    soup = fetch_page()
    meteor_events = build_events(soup, today)
    if len(meteor_events) < 4:
        raise SystemExit(
            f"Seulement {len(meteor_events)} pluies reconnues sur le calendrier IMO ; "
            "aucune modification effectuée par sécurité."
        )

    other_events = [
        event for event in current
        if event.get("category") != "Pluie d’étoiles filantes"
        and event.get("category") != "Pluie d' étoiles filantes"
    ]
    combined = other_events + meteor_events
    combined.sort(key=lambda event: event.get("date", "9999-12-31"))

    DATA_FILE.write_text(
        json.dumps(combined, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Agenda actualisé : {len(meteor_events)} pluies de météores "
        f"récupérées depuis l’IMO ; {len(other_events)} autres événements conservés."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Échec de l’actualisation : {error}", file=sys.stderr)
        raise
