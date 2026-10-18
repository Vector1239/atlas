"""Test every source in config/sources.toml once and report what works.

Run with ./gl check after installing, and again whenever a brief looks thin.
Nothing is written to state; fix or disable the sources marked ✗.
"""
from __future__ import annotations

import os
import re
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gl_common as gl  # noqa: E402
import job_scan  # noqa: E402


class Skipped(Exception):
    pass


def check(name: str, func) -> bool | None:
    start = time.monotonic()
    try:
        detail = func()
    except Skipped as exc:
        print(f"· {name:<48} {exc}")
        return None
    except RuntimeError as exc:
        print(f"✗ {name:<48} {exc}")
        return False
    except Exception as exc:
        print(f"✗ {name:<48} {gl.short_error(exc)}")
        return False
    print(f"✓ {name:<48} {detail}  ({time.monotonic() - start:.1f}s)")
    return True


def main() -> None:
    cfg = gl.load_config()
    if not cfg:
        sys.exit("config/sources.toml not found")
    results = []

    print("News feeds")
    for feed in cfg.get("news", []):
        if feed.get("enabled", True) is False:
            print(f"· {feed['name']:<48} disabled")
            continue
        def news_check(url=feed["url"]):
            items = gl.parse_feed(gl.http_get(url))
            if not items:
                raise ValueError("feed parsed but has no items")
            dated = sum(1 for i in items if i["published"])
            return f"{len(items)} items, {dated} dated, newest: {items[0]['title'][:50]!r}"
        results.append(check(feed["name"], news_check))

    print("\nWeather, Mensa")
    home = cfg.get("home", {})
    results.append(check("Open-Meteo", lambda: "ok" if gl.http_json(
        "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(
            {"latitude": home.get("lat"), "longitude": home.get("lon"), "daily": "weather_code",
             "timezone": home.get("timezone", "Europe/Berlin")}))["daily"] else "empty"))

    def mensa_check():
        canteens = gl.http_json("https://openmensa.org/api/v2/canteens?" + urllib.parse.urlencode(
            {"near[lat]": home.get("uni_lat"), "near[lng]": home.get("uni_lon"),
             "near[dist]": cfg.get("brief", {}).get("mensa_radius_km", 6)}))
        names = [c["name"] for c in canteens if "trier" in f"{c.get('name')} {c.get('city')}".lower()]
        return f"{len(names)} Trier canteen(s): {', '.join(names[:4]) or 'none listed'}"
    results.append(check("OpenMensa", mensa_check))

    print("\nJobs")
    matcher = job_scan.Matcher(cfg.get("jobs", {}))
    for name, fetch in [("Bundesagentur (ring 0 searches)", job_scan.fetch_bundesagentur),
                        ("Arbeitnow", job_scan.fetch_arbeitnow),
                        ("JSearch (all rings)", job_scan.fetch_jsearch)]:
        rings = {0} if fetch is job_scan.fetch_bundesagentur else {0, 1, 2, 3}
        def job_check(fetch=fetch, rings=rings):
            status: list[str] = []
            jobs = fetch(cfg, rings, matcher, status)
            if not status:
                raise Skipped("no searches configured")
            line = status[0]
            if line.startswith("·"):
                raise Skipped(line[2:])
            if line.startswith("✗"):
                raise RuntimeError(line[2:])
            return f"{line[2:]}" + (f"; e.g. {jobs[0]['title'][:40]!r}" if jobs else "")
        results.append(check(name, job_check))

    print("\nYour files")
    profile = gl.project_home() / "profile.md"
    print(("✓" if profile.exists() else "✗") + f" profile.md {'found' if profile.exists() else 'missing'}")
    if profile.exists() and re.search(r"<(?!!--)[^>\n]+>", profile.read_text(encoding="utf-8")):
        print("  ! profile.md still has <placeholders> to fill in")
    try:
        real = gl.load_deadlines()
        examples = len(gl.load_deadlines(include_examples=True)) - len(real)
        print(f"✓ data/deadlines.toml: {len(real)} deadline(s)"
              + (f", {examples} example(s) ignored until you remove `example = true`" if examples else ""))
    except Exception as exc:
        print(f"✗ data/deadlines.toml: {exc}")

    results = [r for r in results if r is not None]
    failed = results.count(False)
    print(f"\n{len(results) - failed} of {len(results)} sources OK." + (" Fix or disable the ✗ ones in config/sources.toml." if failed else ""))


if __name__ == "__main__":
    main()
