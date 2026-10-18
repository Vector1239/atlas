"""Live events from Ticketmaster's Discovery API (free key): around home, Germany's big cities and European capitals.

Concerts, theatre, comedy, festivals and sports with dates, prices and venue coordinates. Each
listing links to its Ticketmaster page. Requests stay far below the free quota (5,000 a day,
2 a second): one sweep of about 30 searches, at most every 12 hours. The key stays on this Mac.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import time
import urllib.parse

import gl_common as gl

API = "https://app.ticketmaster.com/discovery/v2/events.json?"
CACHE_SECONDS = 12 * 3600
WINDOW_DAYS = 45
# Search centres (a 20 km radius covers each city); pins come from the venues themselves.
GERMANY = [("Berlin", 52.520, 13.405), ("Hamburg", 53.551, 9.993), ("Munich", 48.137, 11.575), ("Cologne", 50.938, 6.960),
           ("Frankfurt", 50.110, 8.682), ("Stuttgart", 48.776, 9.183), ("Düsseldorf", 51.227, 6.773), ("Leipzig", 51.340, 12.375),
           ("Dresden", 51.050, 13.738), ("Hanover", 52.375, 9.732), ("Nuremberg", 49.452, 11.077), ("Bremen", 53.079, 8.802)]
EUROPE = [("Amsterdam", 52.370, 4.895), ("Brussels", 50.850, 4.352), ("Vienna", 48.208, 16.373), ("Zurich", 47.377, 8.541),
          ("Paris", 48.857, 2.352), ("Copenhagen", 55.676, 12.568), ("Prague", 50.075, 14.438), ("Warsaw", 52.230, 21.012),
          ("Madrid", 40.417, -3.704), ("Barcelona", 41.385, 2.173), ("Dublin", 53.350, -6.260), ("London", 51.507, -0.128),
          ("Stockholm", 59.329, 18.069), ("Oslo", 59.914, 10.752)]
CATEGORIES = {"Music": "Music", "Arts & Theatre": "Culture", "Sports": "Sports", "Film": "Film", "Family": "Family"}
# Bump when the event shape changes so the next refresh replaces older cached rows.
SCHEMA = 2
TEAM_SPORTS = {"Football", "Soccer", "Basketball", "Hockey", "Ice Hockey", "Handball", "Volleyball", "Rugby", "Baseball", "American Football"}
STAGE = {"Theatre": "theatre show", "Comedy": "comedy show", "Musical": "musical", "Opera": "opera", "Dance": "dance performance",
         "Classical": "classical performance", "Magic & Illusion": "magic show", "Circus & Specialty Acts": "circus show",
         "Children's Theatre": "children's theatre show", "Spectacular": "show", "Cultural": "cultural event"}
SYMBOLS = {"EUR": "€", "GBP": "£", "USD": "$", "CHF": "CHF ", "DKK": "DKK ", "SEK": "SEK ", "NOK": "NOK ", "PLN": "PLN ", "CZK": "CZK "}


def _key_path(state_dir):
    return state_dir / "event_credentials.json"


def credentials(state_dir):
    saved = gl.load_json(_key_path(state_dir), None)
    return saved.get("key", "") if isinstance(saved, dict) else os.environ.get("TICKETMASTER_API_KEY", "")


def save_key(state_dir, key):
    if not isinstance(key, str) or len(key) > 200 or any(c.isspace() for c in key):
        raise ValueError("Enter a valid Ticketmaster API key.")
    path = _key_path(state_dir)
    with gl.file_lock(path):
        tmp = path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump({"key": key}, handle)
        os.replace(tmp, path)


def cached(state_dir):
    return gl.load_json(state_dir / "live_events.json", {})


def geohash(lat, lon, precision=9):
    alphabet, bits, value, even, out = "0123456789bcdefghjkmnpqrstuvwxyz", 0, 0, True, ""
    lats, lons = [-90.0, 90.0], [-180.0, 180.0]
    while len(out) < precision:
        span, coordinate = (lons, lon) if even else (lats, lat)
        middle = (span[0] + span[1]) / 2
        value = value * 2 + (coordinate >= middle)
        span[0 if coordinate >= middle else 1] = middle
        even, bits = not even, bits + 1
        if bits == 5:
            out, bits, value = out + alphabet[value], 0, 0
    return out


def distance_km(lat1, lon1, lat2, lon2):
    rad = math.radians
    a = math.sin(rad(lat2 - lat1) / 2) ** 2 + math.cos(rad(lat1)) * math.cos(rad(lat2)) * math.sin(rad(lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))


def _named(value):
    name = gl.clean_text((value or {}).get("name", ""), 60)
    return "" if name.casefold() in ("undefined", "other", "miscellaneous", "") else name


def summary(segment, genre, subgenre, lineup, venue, city):
    """A one-line "what is this" from Ticketmaster's classification and line-up, e.g. "Rock concert with Muse at Arena, Berlin"."""
    place = " at " + ", ".join(p for p in (venue, city) if p) if venue or city else ""
    if segment == "Music":
        style = genre or subgenre
        what = f"{style} concert" if style else "Concert"
        acts = lineup[:3]
        return what + (" with " + ", ".join(acts[:-1]) + " and " + acts[-1] if len(acts) > 1 else f" with {acts[0]}" if acts else "") + place
    if segment == "Sports":
        sport = genre or subgenre
        if sport in TEAM_SPORTS and len(lineup) >= 2:
            return f"{sport} match: {lineup[0]} vs {lineup[1]}{place}"
        return (f"{sport} event" if sport else "Sports event") + (f" with {lineup[0]}" if lineup else "") + place
    if segment == "Arts & Theatre":
        what = STAGE.get(genre) or (f"{genre} show" if genre else "Stage show")
        return what[0].upper() + what[1:] + (f" with {lineup[0]}" if lineup else "") + place
    if segment == "Film":
        return (f"{genre} film screening" if genre else "Film screening") + place
    if segment == "Family" or genre == "Family":
        return "Family event" + (f" with {lineup[0]}" if lineup else "") + place
    return ("Event with " + lineup[0] if lineup else (genre + " event" if genre else "Event")) + place


def normalize(item, home, today):
    """One Ticketmaster event in Atlas' event shape, or None when it has no firm date or was cancelled."""
    if not isinstance(item, dict) or not item.get("name") or not str(item.get("url", "")).startswith("https://"):
        return None
    dates = item.get("dates") or {}
    start = dates.get("start") or {}
    if start.get("dateTBD") or start.get("dateTBA") or not start.get("localDate"):
        return None
    state = str((dates.get("status") or {}).get("code") or "").lower()
    if state in ("cancelled", "canceled"):
        return None
    end = (dates.get("end") or {}).get("localDate") or start["localDate"]
    try:
        if dt.date.fromisoformat(end) < today or dt.date.fromisoformat(start["localDate"]) > dt.date.fromisoformat(end):
            return None
    except ValueError:
        return None
    venue = ((item.get("_embedded") or {}).get("venues") or [{}])[0] or {}
    city = gl.clean_text((venue.get("city") or {}).get("name", ""), 80)
    country = gl.clean_text((venue.get("country") or {}).get("name", ""), 60)
    code = str((venue.get("country") or {}).get("countryCode") or "").upper()
    location, distance = None, None
    try:
        lat, lon = float(venue["location"]["latitude"]), float(venue["location"]["longitude"])
        if abs(lat) <= 90 and abs(lon) <= 180 and (lat, lon) != (0.0, 0.0):
            location = {"lat": round(lat, 5), "lon": round(lon, 5), "name": city, "label": city, "country": country,
                        "precision": "venue", "source": "Ticketmaster venue"}
            distance = distance_km(home["lat"], home["lon"], lat, lon)
    except (KeyError, TypeError, ValueError):
        pass
    kind = ((item.get("classifications") or [{}])[0] or {})
    segment = (kind.get("segment") or {}).get("name", "")
    genre, subgenre = _named(kind.get("genre")), _named(kind.get("subGenre"))
    subgenre = "" if subgenre == genre else subgenre
    lineup = [name for name in (_named(a) for a in ((item.get("_embedded") or {}).get("attractions") or [])[:4] if isinstance(a, dict)) if name]
    prices = [p for p in item.get("priceRanges") or [] if isinstance(p, dict) and isinstance(p.get("min"), (int, float))]
    price = "Tickets on Ticketmaster"
    if prices:
        symbol = SYMBOLS.get(str(prices[0].get("currency") or "").upper(), "")
        low, high = prices[0]["min"], prices[0].get("max") or prices[0]["min"]
        price = f"{symbol}{low:.0f}" + (f"–{symbol}{high:.0f}" if high > low else "")
    about = gl.clean_text(item.get("description") or item.get("info") or "", 600)
    note = gl.clean_text(item.get("pleaseNote") or "", 400)
    when = (start.get("localTime") or "")[:5]
    return {"id": "tm-" + str(item.get("id") or hashlib.sha256(item["url"].encode()).hexdigest()[:16]), "title": gl.clean_text(item["name"], 200),
            "start": start["localDate"], "end": end, "time_note": (f"{when} · local time" if when else "Time on the listing")
            + (" · postponed" if state == "postponed" else " · rescheduled" if state == "rescheduled" else ""),
            "city": city, "country": country, "country_code": code, "venue": gl.clean_text(venue.get("name", ""), 120),
            "area": "Trier" if distance is not None and distance <= 40 else "Germany" if code == "DE" else "Europe",
            "category": CATEGORIES.get(segment, "Other"), "genre": genre, "subgenre": subgenre, "lineup": lineup, "price": price,
            "description": summary(segment, genre, subgenre, lineup, gl.clean_text(venue.get("name", ""), 120), city) + ".",
            "about": "" if about == note else about, "note": note,
            "source": "Ticketmaster", "url": item["url"], "checked_at": today.isoformat(), "location": location}


def searches(home):
    yield "Around home", home["lat"], home["lon"], 150, 150
    for name, lat, lon in GERMANY:
        yield name, lat, lon, 20, 20
    for name, lat, lon in EUROPE:
        yield name, lat, lon, 20, 12


def refresh(state_dir, home, today, fetch=None, pause=0.6, force=False):
    """Sweep the searches when the 12-hour cache is due; returns the cache. Failures keep the previous events."""
    key = credentials(state_dir)
    cache = cached(state_dir)
    if not key or (not force and cache.get("schema") == SCHEMA and time.time() - cache.get("at", 0) < CACHE_SECONDS):
        return cache
    fetch = fetch or gl.http_json
    window = {"startDateTime": f"{today:%Y-%m-%d}T00:00:00Z",
              "endDateTime": f"{today + dt.timedelta(days=WINDOW_DAYS):%Y-%m-%d}T23:59:59Z"}
    found, seen, errors = [], set(), []
    for name, lat, lon, radius, size in searches(home):
        query = {"apikey": key, "geoPoint": geohash(lat, lon), "radius": radius, "unit": "km", "size": size,
                 "sort": "date,asc", "locale": "*", **window}
        try:
            data = fetch(API + urllib.parse.urlencode(query), timeout=20)
        except Exception as exc:  # the URL holds the key, so only the short error is kept
            errors.append(f"{name}: {gl.short_error(exc)}")
            if any(code in errors[-1] for code in ("HTTP 401", "HTTP 403", "HTTP 429")):
                break
            continue
        for item in ((data or {}).get("_embedded") or {}).get("events") or []:
            row = normalize(item, home, today)
            marker = row and (row["title"].casefold(), row["start"], row["venue"].casefold())
            if row and marker not in seen:
                seen.add(marker)
                found.append(row)
        time.sleep(pause)
    if not found and errors:
        cache.update(error="; ".join(errors[:2]), at=time.time(), schema=SCHEMA)  # don't hammer a rejected key; retry after 12 hours
    else:
        cache = {"at": time.time(), "schema": SCHEMA, "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                 "events": sorted(found, key=lambda row: row["start"]), "error": "; ".join(errors[:2])}
    gl.save_json(state_dir / "live_events.json", cache)
    return cache
