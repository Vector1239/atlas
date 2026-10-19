"""Collect the raw material for the morning brief.

Hermes runs this right before the "Morning brief" cron job and passes everything
it prints to the agent, which turns it into the message you get on Telegram.
Run it by hand with `./gl brief` (which adds --dry-run, so nothing is marked as seen).
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gl_common as gl  # noqa: E402

RING_NAMES = {0: "Trier", 1: "Region: Luxembourg, Saarland, Rhineland-Palatinate",
              2: "Germany", 3: "Europe"}
WMO = {0: "clear", 1: "mainly clear", 2: "partly cloudy", 3: "overcast", 45: "fog",
       48: "freezing fog", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
       56: "freezing drizzle", 57: "freezing drizzle", 61: "light rain", 63: "rain",
       65: "heavy rain", 66: "freezing rain", 67: "freezing rain", 71: "light snow",
       73: "snow", 75: "heavy snow", 77: "snow grains", 80: "rain showers",
       81: "rain showers", 82: "heavy rain showers", 85: "snow showers",
       86: "heavy snow showers", 95: "thunderstorm", 96: "thunderstorm with hail",
       99: "thunderstorm with hail"}
SEEN_DAYS = 3  # don't repeat a headline shown in the last few briefs


def weather(cfg: dict, status: list) -> list[str]:
    home = cfg.get("home", {})
    query = urllib.parse.urlencode({
        "latitude": home.get("lat", 49.7499), "longitude": home.get("lon", 6.6371),
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                 "precipitation_probability_max,wind_speed_10m_max",
        "timezone": home.get("timezone", "Europe/Berlin"), "forecast_days": 2})
    try:
        daily = gl.http_json(f"https://api.open-meteo.com/v1/forecast?{query}")["daily"]
    except Exception as exc:
        status.append(f"✗ Weather (Open-Meteo): {gl.short_error(exc)}")
        return []
    status.append("✓ Weather (Open-Meteo)")
    lines = []
    for i, label in enumerate(["today", "tomorrow"]):
        lines.append(
            f"{label}: {WMO.get(daily['weather_code'][i], 'code ' + str(daily['weather_code'][i]))}, "
            f"{daily['temperature_2m_min'][i]:.0f}–{daily['temperature_2m_max'][i]:.0f} °C, "
            f"rain chance {daily['precipitation_probability_max'][i]}%, "
            f"wind up to {daily['wind_speed_10m_max'][i]:.0f} km/h")
    return lines


def _canteens(cfg: dict) -> list[dict]:
    cache_path = gl.state_dir() / "openmensa_canteens.json"
    cache = gl.load_json(cache_path, {})
    fetched = cache.get("fetched")
    if fetched and dt.date.fromisoformat(fetched) > dt.date.today() - dt.timedelta(days=30):
        return cache.get("canteens", [])
    home, brief = cfg.get("home", {}), cfg.get("brief", {})
    query = urllib.parse.urlencode({
        "near[lat]": home.get("uni_lat", 49.7466), "near[lng]": home.get("uni_lon", 6.6873),
        "near[dist]": brief.get("mensa_radius_km", 6)})
    canteens = gl.http_json(f"https://openmensa.org/api/v2/canteens?{query}")
    canteens = [c for c in canteens if "trier" in f"{c.get('name', '')} {c.get('city', '')}".lower()]
    try:
        gl.save_json(cache_path, {"fetched": dt.date.today().isoformat(), "canteens": canteens})
    except OSError:
        pass  # read-only checkout (e.g. inside the Docker sandbox): just skip the cache
    return canteens


def mensa_menu(cfg: dict, status: list, today: dt.date) -> list[dict]:
    """Today's meals per canteen: [{"canteen", "open", "meals": [{"name", "category", "student"}]}]."""
    brief = cfg.get("brief", {})
    try:
        canteens = _canteens(cfg)
    except Exception as exc:
        status.append(f"✗ Mensa (OpenMensa): {gl.short_error(exc)}")
        return []
    wanted = (brief.get("mensa_name_filter") or "").lower()
    if wanted:
        canteens = [c for c in canteens if wanted in c.get("name", "").lower()]
    if not canteens:
        status.append("· Mensa: no Trier canteen found on OpenMensa")
        return []
    menu = []
    for canteen in canteens[: brief.get("mensa_max", 2)]:
        url = f"https://openmensa.org/api/v2/canteens/{canteen['id']}/days/{today.isoformat()}/meals"
        try:
            meals = gl.http_json(url)
        except Exception:
            menu.append({"canteen": canteen["name"], "open": False, "meals": []})
            continue
        rows = []
        for meal in meals[:12]:
            price = (meal.get("prices") or {}).get("students")
            rows.append({"name": meal.get("name", "?"), "category": meal.get("category", ""),
                         "student": float(price) if isinstance(price, (int, float)) else None})
        menu.append({"canteen": canteen["name"], "open": True, "meals": rows})
    status.append(f"✓ Mensa (OpenMensa): {len(canteens)} canteen(s)")
    return menu


def mensa_lines(menu: list[dict]) -> list[str]:
    lines = []
    for canteen in menu:
        if not canteen["open"]:
            lines.append(f"{canteen['canteen']}: closed or no menu today")
            continue
        lines.append(f"{canteen['canteen']}:")
        for meal in canteen["meals"][:6]:
            price_text = f" — €{meal['student']:.2f} students" if meal["student"] is not None else ""
            lines.append(f"  - {meal['name']} ({meal['category']}){price_text}")
    return lines


def mensa(cfg: dict, status: list, today: dt.date) -> list[str]:
    return mensa_lines(mensa_menu(cfg, status, today))


def deadlines(today: dt.date, status: list) -> list[str]:
    try:
        entries = gl.load_deadlines()
    except Exception as exc:
        status.append(f"✗ data/deadlines.toml: {exc}")
        return []
    lines = []
    for entry in entries:
        days = (entry["date"] - today).days
        if -7 <= days <= 45:
            when = "TODAY" if days == 0 else (f"{-days} days OVERDUE" if days < 0 else f"in {days} days")
            lines.append(f"- {entry['date'].isoformat()} ({when}) [{entry.get('category', 'other')}] "
                         f"{entry.get('title', '?')}")
    return lines


def news(cfg: dict, status: list, current: dt.datetime, dry_run: bool) -> dict[int, list[str]]:
    brief = cfg.get("brief", {})
    hours = 72 if current.weekday() == 0 else brief.get("news_hours", 30)
    cutoff = current - dt.timedelta(hours=hours)
    per_feed = brief.get("max_per_feed", 6)
    seen_path = gl.state_dir() / "news_seen.json"
    seen = gl.load_json(seen_path, {})
    keep_after = (current.date() - dt.timedelta(days=SEEN_DAYS)).isoformat()
    seen = {key: day for key, day in seen.items() if day >= keep_after}
    shown_now: set[str] = set()
    by_ring: dict[int, list[str]] = {}

    for feed in cfg.get("news", []):
        if feed.get("enabled", True) is False:
            continue
        try:
            items = gl.parse_feed(gl.http_get(feed["url"]))
        except Exception as exc:
            status.append(f"✗ {feed['name']}: {gl.short_error(exc)}")
            continue
        fresh = [i for i in items if i["published"] is None or i["published"] >= cutoff]
        fresh.sort(key=lambda i: i["published"] or cutoff, reverse=True)
        kept = 0
        for item in fresh:
            key = gl.norm(item["title"])[:90]
            if not key or key in seen or key in shown_now:
                continue
            shown_now.add(key)
            when = item["published"].astimezone(current.tzinfo).strftime("%a %H:%M") if item["published"] else "?"
            source = f" — {item['source']}" if item["source"] else ""
            by_ring.setdefault(int(feed.get("ring", 2)), []).append(
                f"- [{feed.get('lang', '?')}] {item['title']}{source} ({feed['name']}, {when})\n"
                f"  {item['link']}")
            kept += 1
            if kept >= per_feed:
                break
        status.append(f"✓ {feed['name']}: {len(items)} items, {kept} new")

    if not dry_run:
        today = current.date().isoformat()
        seen.update({key: today for key in shown_now})
        gl.save_json(seen_path, seen)
    return by_ring


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="don't remember shown headlines")
    args = parser.parse_args()

    cfg = gl.load_config()
    current = gl.now(cfg)
    status: list[str] = []
    out = [f"# MORNING DATA — {current.strftime('%A %d %B %Y, %H:%M')} ({cfg.get('home', {}).get('timezone', 'Europe/Berlin')})",
           "", "## PROFILE", gl.read_profile(), ""]

    out += ["## WEATHER " + cfg.get("home", {}).get("city", "Trier")] + (weather(cfg, status) or ["(unavailable)"]) + [""]
    out += ["## MENSA"] + (mensa(cfg, status, current.date()) or ["(nothing today)"]) + [""]
    out += ["## DEADLINES (next 45 days, and overdue)"] + (deadlines(current.date(), status) or ["(none)"]) + [""]
    out += ["## WORK DAYS", gl.workdays_line(gl.workdays_summary(current.year)), ""]

    by_ring = news(cfg, status, current, args.dry_run)
    for ring in sorted(RING_NAMES):
        out.append(f"## NEWS ring {ring}: {RING_NAMES[ring]}")
        out += by_ring.get(ring) or ["(nothing new)"]
        out.append("")

    out += ["## SOURCE STATUS"] + status
    print("\n".join(out))


if __name__ == "__main__":
    main()
