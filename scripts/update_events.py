#!/usr/bin/env python3
"""Actualise les phases lunaires USNO et les éclipses IMCCE.

Le script échoue sans modifier le JSON si une source est indisponible ou
si sa structure ne correspond plus aux données attendues.
"""
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


OPALE = "https://opale.imcce.fr/api/v1/phenomena"
DATA_FILE = Path("data/evenements.json")
PARIS = ZoneInfo("Europe/Paris")

PHASES = {
    "NewMoon": "Nouvelle Lune",
    "FirstQuarter": "Premier quartier",
    "FullMoon": "Pleine Lune",
    "LastQuarter": "Dernier quartier",
}


def get_json(url):
    request = Request(url, headers={"User-Agent": "AstroClubAgenda/2.0"})
    with urlopen(request, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def local_datetime(value):
    # OPALE renvoie des instants UTC sans suffixe Z.
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(PARIS)


def moon_events(years, today):
    # US Naval Observatory : phases primaires en temps universel (UTC).
    generated = []
    phase_names = {
        "New Moon": "Nouvelle Lune",
        "First Quarter": "Premier quartier",
        "Full Moon": "Pleine Lune",
        "Last Quarter": "Dernier quartier",
    }
    for year in years:
        payload = get_json(f"https://aa.usno.navy.mil/api/moon/phases/year?year={year}")
        rows = payload.get("phasedata", [])
        if payload.get("error") or not isinstance(rows, list) or len(rows) < 40:
            raise RuntimeError(f"Réponse USNO incomplète pour les phases lunaires {year}.")
        for row in rows:
            phase = phase_names.get(row.get("phase"))
            if not phase:
                continue
            instant_utc = (
                f"{int(row['year']):04d}-{int(row['month']):02d}-"
                f"{int(row['day']):02d}T{row['time']}:00+00:00"
            )
            local = local_datetime(instant_utc)
            if local.date() < today:
                continue
            generated.append({
                "date": local.date().isoformat(),
                "endDate": None,
                "title": phase,
                "category": "Phase de la Lune",
                "scope": "france",
                "visibility": "Phase astronomique observable depuis la France si la Lune est au-dessus de l’horizon et si le ciel est dégagé.",
                "summary": f"{phase} à {local:%H:%M} (heure de Paris).",
                "details": "Instant de phase calculé par l’US Naval Observatory ; l’aspect de la Lune évolue autour de cet instant.",
                "time": f"{local:%H:%M} — heure locale de Paris (conversion depuis UTC).",
                "where": "Observer la Lune si elle est au-dessus de l’horizon.",
                "direction": "Dépend de l’heure et de la position de la Lune ; non calculée ici.",
                "altitude": "Non calculée automatiquement.",
                "moon": phase,
                "weather": "Vérifier la couverture nuageuse locale.",
                "equipment": "Œil nu ; jumelles ou télescope facultatifs.",
                "tips": "La nouvelle Lune est difficile à observer dans l’éclat du Soleil ; ne jamais pointer un instrument vers le Soleil sans filtre solaire adapté.",
                "source": "https://aa.usno.navy.mil/data/api",
            })
    if len(generated) < 20:
        raise RuntimeError("Trop peu de phases lunaires futures reçues depuis l’USNO.")
    return generated

def find_eclipse_rows(value):
    found = []
    if isinstance(value, dict):
        if isinstance(value.get("calendarDate"), str) and isinstance(value.get("events"), dict):
            found.append(value)
        else:
            for child in value.values():
                found.extend(find_eclipse_rows(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(find_eclipse_rows(child))
    return found


def eclipse_events(years, today):
    generated = []
    for year in years:
        for body, solar in ((10, True), (301, False)):
            url = f"{OPALE}/eclipses/{body}/{year}"
            payload = get_json(url)
            rows = find_eclipse_rows(payload.get("response", {}))
            if not rows:
                raise RuntimeError(f"Aucune éclipse reconnue dans la réponse OPALE {body}/{year}.")
            for row in rows:
                try:
                    day = date.fromisoformat(row["calendarDate"])
                except (KeyError, ValueError):
                    raise RuntimeError("Date d'éclipse invalide dans la réponse OPALE.")
                if day < today:
                    continue
                kind = str(row.get("type", "")).lower()
                if solar:
                    if "annular" in kind:
                        title = "Éclipse annulaire de Soleil"
                    elif "total" in kind:
                        title = "Éclipse totale de Soleil"
                    elif "partial" in kind:
                        title = "Éclipse partielle de Soleil"
                    else:
                        raise RuntimeError(f"Type d'éclipse solaire inconnu : {row.get('type')}")
                    if day.isoformat() == "2027-02-06":
                        scope = "voyage"
                        visibility = "Non visible depuis la France métropolitaine ; la zone annulaire se situe dans l’hémisphère Sud."
                        where = "Trajectoire à consulter sur la carte officielle de l’IMCCE/NASA."
                    elif day.isoformat() == "2027-08-02":
                        scope = "france"
                        visibility = "Éclipse partielle depuis la France ; totalité dans une bande traversant notamment le sud de l’Espagne et l’Afrique du Nord."
                        where = "Depuis la France : phase partielle. Pour la totalité, choisir un site précisément situé dans la bande de totalité."
                    else:
                        scope = "voyage"
                        visibility = "Zone de visibilité à vérifier sur la carte officielle pour le lieu d’observation."
                        where = "Trajectoire à consulter sur la carte officielle de l’IMCCE."
                    equipment = "Filtre solaire certifié indispensable pendant toutes les phases partielles et annulaires. Ne jamais regarder le Soleil sans protection adaptée."
                    tips = "Vérifier les circonstances locales et la trajectoire officielle avant tout déplacement."
                else:
                    if "penumbral" in kind:
                        title = "Éclipse pénombrale de Lune"
                    elif "partial" in kind:
                        title = "Éclipse partielle de Lune"
                    elif "total" in kind:
                        title = "Éclipse totale de Lune"
                    else:
                        raise RuntimeError(f"Type d'éclipse lunaire inconnu : {row.get('type')}")
                    scope = "france"
                    visibility = "Visibilité depuis la France à confirmer avec les circonstances locales et la hauteur de la Lune."
                    where = "Lune ; choisir un horizon dégagé."
                    equipment = "Œil nu ; jumelles facultatives."
                    tips = "Une éclipse pénombrale est discrète et peut être difficile à distinguer à l’œil nu."

                greatest = row.get("events", {}).get("greatest", {}).get("date")
                local_time = local_datetime(greatest) if greatest else None
                event_date = local_time.date() if local_time else day
                time_text = (
                    f"Maximum à {local_time:%H:%M} (heure de Paris), calcul global ; "
                    "les circonstances locales peuvent différer."
                    if local_time else "Horaires locaux à consulter dans les circonstances détaillées."
                )
                generated.append({
                    "date": event_date.isoformat(),
                    "endDate": None,
                    "title": title,
                    "category": "Éclipse",
                    "scope": scope,
                    "visibility": visibility,
                    "summary": f"{title} le {event_date.strftime('%d/%m/%Y')}.",
                    "details": "Éphéméride calculée par l’IMCCE (service OPALE). Vérifier la carte de visibilité et les circonstances locales avant observation ou déplacement.",
                    "time": time_text,
                    "where": where,
                    "direction": "Dépend du lieu et de l’heure ; ne pas déduire une direction sans circonstances locales.",
                    "altitude": "Non calculée pour le site d’observation.",
                    "moon": "La Lune est l’astre occultant ou occulté selon le phénomène.",
                    "weather": "Vérifier les prévisions météorologiques du site choisi.",
                    "equipment": equipment,
                    "tips": tips,
                    "source": "https://opale.imcce.fr/webservices/api.html",
                })
    return generated


def main():
    today = datetime.now(PARIS).date()
    if not DATA_FILE.exists():
        raise SystemExit(f"Fichier introuvable : {DATA_FILE}")
    with DATA_FILE.open(encoding="utf-8") as stream:
        current = json.load(stream)
    if not isinstance(current, list):
        raise SystemExit("Le fichier JSON doit contenir une liste d'événements.")

    # Toutes les sources sont téléchargées et validées avant de toucher au fichier.
    generated_moons = moon_events((today.year, today.year + 1), today)
    generated_eclipses = eclipse_events((today.year, today.year + 1), today)

    automatic_categories = {
        "Phase de la Lune", "Éclipse"
    }
    manual = [e for e in current if e.get("category") not in automatic_categories]
    merged = manual + generated_moons + generated_eclipses
    merged.sort(key=lambda e: (e.get("date", "9999-12-31"), e.get("title", "")))

    # Contrôle final minimal avant écriture atomique.
    required = ("date", "title", "category", "scope", "summary")
    seen = set()
    for event in merged:
        if any(not isinstance(event.get(key), str) or not event[key].strip() for key in required):
            raise RuntimeError(f"Événement incomplet : {event.get('title', 'sans titre')}")
        date.fromisoformat(event["date"])
        key = (event["date"], event["title"])
        if key in seen:
            raise RuntimeError(f"Doublon détecté : {key}")
        seen.add(key)

    temporary = DATA_FILE.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(DATA_FILE)
    print(
        f"OK : essaims conservés, "
        f"{len(generated_moons)} phases lunaires USNO, "
        f"{len(generated_eclipses)} éclipses IMCCE ; "
        f"{len(manual)} événements manuels conservés."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Échec de l'actualisation ; aucun JSON modifié : {error}", file=sys.stderr)
        raise
