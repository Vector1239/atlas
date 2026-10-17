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
        items.append({**row, "ongoing": start < today, "stale": (today - checked).days > 14})
    return {"items": sorted(items, key=lambda row: row["start"]),
            "calendars": EVENT_CATALOG["calendars"], "checked_at": EVENT_CATALOG["checked_at"]}
