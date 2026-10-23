"""English job titles, explicit source metadata, and a dated event selection."""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
import re

from job_language import german_requirement
import job_insights

CONTENT = Path(__file__).parent / "content"
TITLE_TRANSLATIONS = json.loads((CONTENT / "job-translations.json").read_text())
EVENT_CATALOG = json.loads((CONTENT / "events.json").read_text())
PLACES = json.loads((CONTENT / "places.json").read_text())
NEWS_TRANSLATIONS = json.loads((CONTENT / "news-translations.json").read_text())


GEOCODED = {}  # cities places.json lacks, looked up with the same geocoder and cached in state/places_cache.json
COUNTRIES = {"DE": "Germany", "LU": "Luxembourg", "NL": "The Netherlands", "AT": "Austria",
             "BE": "Belgium", "FR": "France", "CH": "Switzerland"}
GEOCODER = "https://geocoding-api.open-meteo.com/v1/search?"


def load_places(path):
    try:
        cache = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    GEOCODED.update({entry["label"]: entry["place"] for entry in cache.values()
                     if isinstance(entry, dict) and isinstance(entry.get("place"), dict)})
    return cache


def geocode(places, path, fetch, limit=40, retry_days=30):
    """Pins for cities places.json lacks: [(city, country code, region)] -> cached Open-Meteo / GeoNames matches.

    Only a populated place whose name matches the listing's city in that country gets a pin; the
    region the listing gives decides between towns with the same name."""
    import time
    import urllib.parse
    cache, looked = load_places(path), 0
    for city, code, region in places:
        key = f"{city}|{code}"
        entry = cache.get(key, {})
        if city in PLACES or code not in COUNTRIES or time.time() - entry.get("at", 0) < retry_days * 86400 or looked >= limit:
            continue
        looked += 1
        base = re.split(r"\s*[,(/]", city)[0].strip()
        names = list(dict.fromkeys([base, re.sub(r"\s+(?:am|an der|im|in der|ob der|bei)\s.+$", "", base)]))
        found = None
        for name in names:
            for language in ("de", "en"):
                try:
                    rows = fetch(GEOCODER + urllib.parse.urlencode({"name": name, "count": 10, "language": language,
                                                                    "countryCode": code, "format": "json"})).get("results") or []
                except Exception:
                    rows = []
                rows = [row for row in rows if row.get("country_code") == code and str(row.get("feature_code", "")).startswith("PPL")
                        and str(row.get("name", "")).casefold() == name.casefold()]
                rows.sort(key=lambda row: (bool(region) and row.get("admin1") != region, -(row.get("population") or 0)))
                if rows:
                    row = rows[0]
                    found = {"lat": round(row["latitude"], 5), "lon": round(row["longitude"], 5), "name": row["name"],
                             "country": COUNTRIES[code], "country_code": code, "region": row.get("admin1", ""),
                             "geonames_id": row.get("id"), "precision": "city"}
                    break
            if found:
                break
        cache[key] = {"label": city, "place": found, "at": time.time()}
        if found:
            GEOCODED[city] = found
    Path(path).write_text(json.dumps(cache, ensure_ascii=False, indent=1))
    return looked


def city_location(city, country="Germany"):
    """Only use verified city matches. Never invent an exact address or unknown pin."""
    place = PLACES.get(city) or GEOCODED.get(city)
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


def timezone_summary(values):
    """Timezone eligibility relative to Germany; accept saved numeric and API string offsets."""
    if not values:
        return "Germany time supported", "Any time zone, including Germany (CET in winter / CEST in summer)."
    minutes = set()
    for value in values:
        raw = str(value).strip().upper().removeprefix("UTC").removeprefix("GMT")
        try:
            if ":" in raw:
                hours, part = raw.split(":", 1)
                amount = abs(int(hours)) * 60 + int(part)
                amount *= -1 if raw.startswith("-") else 1
            else:
                amount = round(float(raw) * 60)
            if -12 * 60 <= amount <= 14 * 60:
                minutes.add(amount)
        except (ValueError, OverflowError):
            continue
    if not minutes:
        return "", ""
    # Himalayas sends every inhabited UTC offset even for unrestricted roles.
    worldwide = {h * 60 for h in range(-11, 15)} | {-570, -210, 210, 270, 330, 345, 390, 525, 570, 630, 765}
    if worldwide <= minutes:
        return "Germany time supported", "Any time zone, including Germany (CET in winter / CEST in summer)."
    def relative(n):
        delta = n - 60  # Himalayas uses standard/winter offsets for country eligibility.
        if delta == 0:
            return "Germany time (CET / CEST)"
        hours, mins = divmod(abs(delta), 60)
        amount = (f"{hours} hour{'s' if hours != 1 else ''}" if hours else "")
        if mins:
            amount += (" " if amount else "") + f"{mins} minutes"
        return f"{amount} {'ahead of' if delta > 0 else 'behind'} Germany (winter)"
    details = "; ".join(relative(n) for n in sorted(minutes))
    label = "Germany time supported" if 60 in minutes else relative(next(iter(minutes))) if len(minutes) == 1 else "Different from Germany time · see details"
    return label, details



def enrich_job(job, translations=None):
    result = dict(job)
    title = job["title"]
    translated = (translations or {}).get(title) or TITLE_TRANSLATIONS.get(title)
    result["title_en"] = translated or (clean_gender(title) if not GERMAN_TITLE.search(title) else None)
    result["translation_needed"] = result["title_en"] is None
    result["flags"] = list(job.get("flags", []))
    result["german_requirement"] = german_requirement(title + ". " + (job.get("text") or ""))
    german = result["german_requirement"]
    if german["status"] == "required" and "german-required" not in result["flags"]:
        result["flags"].append("german-required")
    elif german["status"] in ("preferred", "not_required", "mentioned"):
        result["flags"] = [flag for flag in result["flags"] if flag != "german-required"]
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
    if job.get("source") == "Himalayas":
        legacy = re.search(r"Timezones:\s*(.*)", job.get("region_name", ""), re.I)
        zones = job.get("remote_timezones")
        if zones is None:
            zones = legacy.group(1).split(",") if legacy else []
        result["timezone_label"], result["timezone_details"] = timezone_summary(zones)
        result["region_name"] = job.get("remote_scope") or re.split(r"\s*·\s*Timezones:", job.get("region_name", ""), flags=re.I)[0] or "Worldwide"
    result["country_name"] = "Remote" if result["city"] == "Remote" else country
    result["field"] = job_insights.family(result)
    result["location"] = city_location(result["city"], country)
    return result


def upcoming_events(today, live=()):
    """Keep ongoing events, remove expired/cancelled entries, and flag old checks.

    `live` adds events from live sources (Ticketmaster); they bring their own venue pins."""
    items = []
    for row in [*EVENT_CATALOG["events"], *live]:
        try:
            start = dt.date.fromisoformat(row["start"])
            end = dt.date.fromisoformat(row.get("end") or row["start"])
            checked = dt.date.fromisoformat(row["checked_at"])
        except (KeyError, ValueError):
            continue
        if end < today or end < start or row.get("cancelled"):
            continue
        items.append({**row, "location": row.get("location") or city_location(row.get("city"), row.get("country", "Germany")),
                      "ongoing": start < today, "stale": (today - checked).days > 14})
    return {"items": sorted(items, key=lambda row: row["start"]),
            "calendars": EVENT_CATALOG["calendars"], "checked_at": EVENT_CATALOG["checked_at"]}
