"""English job titles, explicit source metadata, and a dated event selection."""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
import re

CONTENT = Path(__file__).parent / "content"
TITLE_TRANSLATIONS = json.loads((CONTENT / "job-translations.json").read_text())
EVENT_CATALOG = json.loads((CONTENT / "events.json").read_text())
PLACES = json.loads((CONTENT / "places.json").read_text())
NEWS_TRANSLATIONS = json.loads((CONTENT / "news-translations.json").read_text())


def city_location(city, country="Germany"):
    """Only use verified city matches. Never invent an exact address or unknown pin."""
    place = PLACES.get(city)
    if not place or place["country"] != {"Netherlands": "The Netherlands"}.get(country, country):
        return None
    return {**place, "label": city, "source": "Open-Meteo / GeoNames"}


def enrich_news(item, translations=None):
    title = item["title"]
    translated = (translations or {}).get(title) or NEWS_TRANSLATIONS.get(title)
    if not translated and item.get("source"):
        # RSS aggregators append the publisher to an otherwise identical title.
        # Reuse a translation only when that suffix matches this known publisher.
        suffix = " - " + item["source"]
        core = title[:-len(suffix)] if title.casefold().endswith(suffix.casefold()) else title
        candidates = {core.casefold(), (core + suffix).casefold()}
        for cache in (translations or {}, NEWS_TRANSLATIONS):
            translated = next((english for original, english in cache.items() if original.casefold() in candidates), None)
            if translated:
                break
    # Feed language describes the source, not necessarily each individual headline.
    german = re.search(r"[äöüß]|\b(?:der|die|das|für|und|im|zum|zur|mit|nach|bei|von|wird|werden|wer|suche|zehn|neue|neues|erneut|ohne|wegen)\b", title, re.I)
    english = re.search(r"\b(?:the|a|an|is|are|for|to|of|in|on|with|how|what|where|i|my|looking|says)\b", title, re.I)
    # A proper name can contain an umlaut in a clearly English headline.
    original_english = bool(english and (not german or re.search(r"\b(?:the|for|to|of|how|what|where|says)\b", title, re.I)))
    title_en = translated or (title if original_english or item.get("lang") == "en" and not german else None)
    return {**item, "title_en": title_en, "translation_needed": title_en is None,
            "translated": bool(translated and translated != title)}

REGIONS = {"RHEINLAND_PFALZ": "Rhineland-Palatinate", "SAARLAND": "Saarland",
           "NORDRHEIN_WESTFALEN": "North Rhine-Westphalia", "HESSEN": "Hesse",
           "BADEN_WUERTTEMBERG": "Baden-Württemberg"}
# Errs towards "German": a wrongly flagged English title only waits for translation, while a
# missed German one would be shown as if it were English.
GERMAN_TITLE = re.compile(
    r"[äöüß]"
    r"|\b(?:und|für|mit|im|bei|zur|zum|der|die|das|des|als|oder|gesucht|duales|studium|referat|schwerpunkt)\b"
    r"|werkstudi|studierende|entwickl|mitarbeit|berater|leiter|leitung|sachbearbeit|referent|ingenieur"
    r"|informatik|kaufm|kauff|fachkraft|hilfskraft|wissenschaft|verwaltung|assistenz|betreuer|techniker"
    r"|daten|analytiker|teilzeit|vollzeit|ausbildung|praktik|arbeit|stelle|beauftragte|vertrieb"
    r"|anforderung|weiterbildung|standort"
    r"|\w(?:ung|keit|heit|schaft)\b|\w(?::|\*|_)in(?:nen)?\b|\w/-?in\b", re.I)


def clean_gender(title):
    return re.sub(r"\s*\((?:m/w/d|w/m/d|w/m/x|m/w/x|m/f/d|all genders)\)", "", title, flags=re.I).strip()


def enrich_job(job, translations=None):
    result = dict(job)
    title = job["title"]
    translated = (translations or {}).get(title) or TITLE_TRANSLATIONS.get(title)
    result["title_en"] = translated or (clean_gender(title) if not GERMAN_TITLE.search(title) else None)
    result["translation_needed"] = result["title_en"] is None
    result["flags"] = list(job.get("flags", []))
    if re.search(r"werkstudi|werkstudent|duales studium|b\.sc\.", title, re.I) and "student-job" not in result["flags"]:
        result["flags"].append("student-job")
    where = job.get("where", "")
    match = re.search(r"\(([\d.,]+)\s*km\)", where)
    distance = job.get("distance_km")
    if distance is None and match:
        distance = match.group(1)
    try:
        distance = float(str(distance).replace(",", "."))
        if not math.isfinite(distance) or distance < 0:
            distance = None
    except (ValueError, TypeError):
        distance = None
    location = re.sub(r"\s*\([\d.,]+\s*km\)", "", where)
    city = job.get("city") or location.split(",")[0].strip()
    region = job.get("region_name") or (location.split(",")[-1].strip() if "," in location else "")
    result.update(city=city if city not in ("?", "") else "Location not provided",
                  region_name=REGIONS.get(region, region.replace("_", " ").title()),
                  distance_km=distance,
                  distance_origin=job.get("distance_origin") or ("Trier" if match and job.get("source") == "Bundesagentur" else ""),
                  source_label="Bundesagentur für Arbeit" if job.get("source") == "Bundesagentur" else job.get("source", "Unknown source"))
    result["distance_from_trier"] = distance if result["distance_origin"].strip().lower() == "trier" else None
    country = {"DE": "Germany", "LU": "Luxembourg", "NL": "The Netherlands", "AT": "Austria",
               "BE": "Belgium", "FR": "France", "CH": "Switzerland"}.get(str(job.get("country", "DE")).upper(), job.get("country", "Germany"))
    result["location"] = city_location(result["city"], country)
    return result


def upcoming_events(today):
    """Keep ongoing events, remove expired/cancelled entries, and flag old checks."""
    items = []
    for row in EVENT_CATALOG["events"]:
        try:
            start = dt.date.fromisoformat(row["start"])
            end = dt.date.fromisoformat(row.get("end") or row["start"])
            checked = dt.date.fromisoformat(row["checked_at"])
        except (KeyError, ValueError):
            continue
        if end < today or end < start or row.get("cancelled"):
            continue
        items.append({**row, "location": city_location(row.get("city"), row.get("country", "Germany")),
                      "ongoing": start < today, "stale": (today - checked).days > 14})
    return {"items": sorted(items, key=lambda row: row["start"]),
            "calendars": EVENT_CATALOG["calendars"], "checked_at": EVENT_CATALOG["checked_at"]}
