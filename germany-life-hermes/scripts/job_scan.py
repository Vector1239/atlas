"""Collect new job postings for the job-scan cron jobs.

Pulls from the Bundesagentur für Arbeit job search, Arbeitnow and (with a key)
Adzuna, keeps postings that match config/sources.toml, drops anything already
sent in an earlier run, and prints the rest for the agent to rank.
When nothing is new it ends with {"wakeAgent": false}, so Hermes skips the LLM.

By hand: ./gl jobs --rings 0,1   (adds --dry-run: nothing is marked as seen)
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gl_common as gl  # noqa: E402

RING_NAMES = {0: "Trier", 1: "Region", 2: "Germany", 3: "Europe"}
BA_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs"
BA_KEY = "jobboerse-jobsuche"  # the public client id the job board's own website uses
SEEN_KEEP_DAYS = 120


class Matcher:
    def __init__(self, jobs_cfg: dict):
        def compile_all(key):
            return [re.compile(p, re.IGNORECASE) for p in jobs_cfg.get(key, [])]
        self.include = compile_all("include")
        self.exclude = compile_all("exclude")
        self.student = compile_all("student")
        self.senior = compile_all("senior")
        self.german = compile_all("german_required")
        self.ring0 = [p.lower() for p in jobs_cfg.get("ring0_places", [])]
        self.ring1 = [p.lower() for p in jobs_cfg.get("ring1_places", [])]

    @staticmethod
    def _any(patterns, text):
        return any(p.search(text) for p in patterns)

    def relevant(self, title: str, extra: str = "") -> bool:
        return self._any(self.include, f"{title} {extra}") and not self._any(self.exclude, title)

    def ring_for_place(self, place: str, remote: bool = False) -> int:
        place = (place or "").lower()
        if any(p in place for p in self.ring0):
            return 0
        if any(p in place for p in self.ring1):
            return 1
        return 2

    def flags(self, job: dict) -> list[str]:
        title, text = job["title"], job.get("text", "")
        flags = []
        if self._any(self.student, title):
            flags.append("student-job")
        if self._any(self.senior, title):
            flags.append("senior")
        if text and self._any(self.german, text):
            flags.append("german-required")
        english = gl.looks_english(text)
        if english is True:
            flags.append("english")
        elif english is False:
            flags.append("posting-in-german")
        if job.get("visa"):
            flags.append("visa-sponsorship")
        if job.get("remote"):
            flags.append("remote")
        return flags


# ---------------------------------------------------------------- sources

def fetch_bundesagentur(cfg: dict, rings: set[int], matcher: Matcher, status: list) -> list[dict]:
    jobs_cfg = cfg.get("jobs", {})
    found, errors, calls = [], [], 0
    for search in jobs_cfg.get("bundesagentur", []):
        ring = int(search.get("ring", 2))
        if ring not in rings:
            continue
        for query in search.get("queries", []):
            params = {"was": query, "size": 50, "page": 1,
                      "veroeffentlichtseit": jobs_cfg.get("max_age_days", 14)}
            if search.get("where"):
                params.update({"wo": search["where"], "umkreis": search.get("radius_km", 50)})
            if jobs_cfg.get("exclude_temp_agencies", True):
                params["zeitarbeit"] = "false"
            calls += 1
            try:
                payload = gl.http_json(f"{BA_URL}?{urllib.parse.urlencode(params)}",
                                       headers={"X-API-Key": BA_KEY})
            except Exception as exc:
                errors.append(f"{query!r}: {gl.short_error(exc)}")
                continue
            for offer in (payload.get("ergebnisliste") or payload.get("stellenangebote") or []):
                locations = offer.get("stellenlokationen") or []
                place = offer.get("arbeitsort") or (locations[0].get("adresse", {}) if locations else {})
                title = offer.get("stellenangebotsTitel") or offer.get("titel") or offer.get("beruf") or ""
                if not matcher.relevant(title, offer.get("beruf", "")):
                    continue
                distance = offer.get("entfernung", place.get("entfernung"))
                where = ", ".join(x for x in [place.get("ort"), place.get("region")] if x)
                if distance not in (None, ""):
                    where += f" ({distance} km)"
                refnr = offer.get("referenznummer") or offer.get("refnr", "")
                found.append({
                    "source": "Bundesagentur", "source_id": refnr, "ring": ring,
                    "title": gl.clean_text(title), "company": gl.clean_text(offer.get("firma") or offer.get("arbeitgeber", "")),
                    "city": place.get("ort", ""), "region_name": place.get("region", ""),
                    "distance_km": distance, "distance_origin": search.get("where", ""),
                    "where": where or "?", "posted": (offer.get("veroeffentlichungszeitraum") or {}).get("von")
                    or offer.get("aktuelleVeroeffentlichungsdatum", ""),
                    "url": f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{urllib.parse.quote(refnr)}",
                    "text": "", "remote": bool(offer.get("homeofficemoeglich")), "visa": False,
                })
    status.append(_status_line("Bundesagentur", calls, errors, len(found)))
    return found


def fetch_arbeitnow(cfg: dict, rings: set[int], matcher: Matcher, status: list) -> list[dict]:
    an_cfg = cfg.get("jobs", {}).get("arbeitnow", {})
    if not an_cfg.get("enabled", True) or not rings & {0, 1, 2}:
        return []
    max_age = dt.timedelta(days=cfg.get("jobs", {}).get("max_age_days", 14))
    by_slug, errors, calls = {}, [], 0
    plan = [(p, False) for p in range(1, an_cfg.get("pages", 3) + 1)]
    plan += [(p, True) for p in range(1, an_cfg.get("visa_pages", 2) + 1)]
    for page, visa in plan:
        params = {"page": page}
        if visa:
            params["visa_sponsorship"] = "true"
        calls += 1
        try:
            payload = gl.http_json(f"https://www.arbeitnow.com/api/job-board-api?{urllib.parse.urlencode(params)}")
        except Exception as exc:
            errors.append(f"page {page}{' (visa)' if visa else ''}: {gl.short_error(exc)}")
            continue
        for item in payload.get("data", []) or []:
            slug = item.get("slug") or item.get("url")
            if not slug:
                continue
            if slug in by_slug:
                by_slug[slug]["visa"] = by_slug[slug]["visa"] or visa
                continue
            created = item.get("created_at")
            posted = dt.datetime.fromtimestamp(created, dt.timezone.utc) if isinstance(created, (int, float)) else None
            if posted and posted < dt.datetime.now(dt.timezone.utc) - max_age:
                continue
            title = item.get("title", "")
            tags = " ".join(item.get("tags") or [])
            if not matcher.relevant(title, tags):
                continue
            ring = matcher.ring_for_place(item.get("location", ""))
            by_slug[slug] = {
                "source": "Arbeitnow", "source_id": slug, "ring": ring,
                "title": gl.clean_text(title), "company": gl.clean_text(item.get("company_name", "")),
                "where": item.get("location") or "?", "posted": posted.date().isoformat() if posted else "",
                "url": item.get("url", ""), "text": gl.clean_text(item.get("description", ""), 4000),
                "remote": bool(item.get("remote")), "visa": visa,
            }
    found = [job for job in by_slug.values() if job["ring"] in rings]
    status.append(_status_line("Arbeitnow", calls, errors, len(found)))
    return found


def fetch_adzuna(cfg: dict, rings: set[int], matcher: Matcher, status: list) -> list[dict]:
    app_id, app_key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    searches = [s for s in cfg.get("jobs", {}).get("adzuna", []) if int(s.get("ring", 2)) in rings]
    if not searches:
        return []
    if not (app_id and app_key):
        status.append("· Adzuna: skipped (no ADZUNA_APP_ID / ADZUNA_APP_KEY)")
        return []
    found, errors = [], []
    for search in searches:
        params = {"app_id": app_id, "app_key": app_key, "what": search.get("what", "data"),
                  "results_per_page": 50, "max_days_old": cfg.get("jobs", {}).get("max_age_days", 14),
                  "content-type": "application/json"}
        if search.get("where"):
            params.update({"where": search["where"], "distance": search.get("radius_km", 50)})
        country = search.get("country", "de")
        try:
            payload = gl.http_json(f"https://api.adzuna.com/v1/api/jobs/{country}/search/1?"
                                   f"{urllib.parse.urlencode(params)}")
        except Exception as exc:
            errors.append(f"{country}/{search.get('what')}: {gl.short_error(exc)}")
            continue
        for item in payload.get("results", []) or []:
            title = gl.clean_text(item.get("title", ""))
            if not matcher.relevant(title):
                continue
            found.append({
                "source": f"Adzuna {country.upper()}", "source_id": str(item.get("id", "")),
                "ring": int(search.get("ring", 2)), "title": title,
                "company": gl.clean_text((item.get("company") or {}).get("display_name", "")),
                "where": (item.get("location") or {}).get("display_name", "?"),
                "posted": (item.get("created") or "")[:10], "url": item.get("redirect_url", ""),
                "text": gl.clean_text(item.get("description", ""), 1500), "remote": False, "visa": False,
            })
    status.append(_status_line("Adzuna", len(searches), errors, len(found)))
    return found


def _status_line(name: str, calls: int, errors: list, kept: int) -> str:
    if errors and len(errors) == calls:
        return f"✗ {name}: all {calls} requests failed ({errors[0]})"
    line = f"✓ {name}: {calls} requests, {kept} matching postings"
    if errors:
        line += f"; {len(errors)} failed ({errors[0]})"
    return line


# ---------------------------------------------------------------- pipeline

def score(job: dict) -> float:
    value = {0: 3, 1: 2, 2: 1, 3: 0}.get(job["ring"], 0)
    flags = job["flags"]
    value += 2 * ("student-job" in flags) + ("english" in flags) + ("visa-sponsorship" in flags)
    value -= 2 * ("senior" in flags) + ("german-required" in flags)
    try:
        age = (dt.date.today() - dt.date.fromisoformat(job["posted"][:10])).days
        value += max(0, 7 - age) / 7
    except ValueError:
        pass
    return value


def recent_feedback(limit: int = 15) -> list[str]:
    path = gl.data_dir() / "job_feedback.csv"
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))[-limit:]
    lines = []
    for row in reversed(rows):
        mark = "👍" if row.get("rating") == "up" else "👎"
        note = f" — {row['note']}" if row.get("note") else ""
        lines.append(f"{mark} {row.get('title', '?')} @ {row.get('company', '?')}{note}")
    return lines


def run(rings: set[int], dry_run: bool) -> str:
    cfg = gl.load_config()
    jobs_cfg = cfg.get("jobs", {})
    matcher = Matcher(jobs_cfg)
    status: list[str] = []
    jobs = (fetch_bundesagentur(cfg, rings, matcher, status)
            + fetch_arbeitnow(cfg, rings, matcher, status)
            + fetch_adzuna(cfg, rings, matcher, status))

    seen_path = gl.state_dir() / "seen_jobs.json"
    seen = gl.load_json(seen_path, {})
    today = dt.date.today().isoformat()
    cutoff = (dt.date.today() - dt.timedelta(days=SEEN_KEEP_DAYS)).isoformat()
    seen = {k: v for k, v in seen.items() if v >= cutoff}

    new_jobs, run_keys = [], set()
    for job in sorted(jobs, key=lambda j: j["ring"]):  # nearest ring wins on duplicates
        keys = {f"{job['source']}:{job['source_id']}", f"tc:{gl.norm(job['title'])}|{gl.norm(job['company'])}"}
        if keys & run_keys or any(k in seen for k in keys):
            continue
        run_keys |= keys
        job["id"] = gl.short_id(sorted(keys)[0])
        job["flags"] = matcher.flags(job)
        new_jobs.append(job)

    new_jobs.sort(key=score, reverse=True)
    limit = jobs_cfg.get("max_items_per_run", 30)
    shown, held_back = new_jobs[:limit], new_jobs[limit:]

    ring_label = " + ".join(RING_NAMES[r] for r in sorted(rings))
    out = [f"# JOB SCAN — {gl.now(cfg).strftime('%a %d %b %Y %H:%M')} — rings: {ring_label}", "",
           "## PROFILE", gl.read_profile(), "",
           "## RECENT FEEDBACK (newest first)"] + (recent_feedback() or ["(none yet)"]) + [""]
    out.append(f"## NEW JOBS ({len(shown)} shown, {len(held_back)} more held back, "
               f"{len(jobs)} matching postings fetched)")
    for job in shown:
        snippet = gl.clean_text(job["text"], 260)
        out += [f"[{job['id']}] {job['title']}",
                f"  company: {job['company'] or '?'} | where: {job['where']} | ring {job['ring']} "
                f"({RING_NAMES.get(job['ring'], '?')}) | source: {job['source']} | posted: {job['posted'] or '?'}",
                f"  flags: {', '.join(job['flags']) or '-'}",
                f"  link: {job['url']}"]
        if snippet:
            out.append(f"  snippet: {snippet}")
    if not shown:
        out.append("(none)")
    out += ["", "## SOURCE STATUS"] + status

    if not dry_run:
        # Held-back jobs stay unseen so a later run can still show them.
        for job in shown:
            seen[f"{job['source']}:{job['source_id']}"] = today
            seen[f"tc:{gl.norm(job['title'])}|{gl.norm(job['company'])}"] = today
        gl.save_json(seen_path, seen)
        index_path = gl.data_dir() / "jobs_index.json"
        with gl.file_lock(index_path):
            index = gl.load_json(index_path, {})
            index = {k: v for k, v in index.items() if v.get("first_seen", today) >= cutoff}
            for job in shown:
                first_seen = index.get(job["id"], {}).get("first_seen", today)
                index[job["id"]] = {k: job[k] for k in ("title", "company", "where", "url", "source", "ring", "flags")}
                index[job["id"]]["first_seen"] = first_seen
            gl.save_json(index_path, index)

    # Nothing new: skip the LLM run. But if every source failed, wake the agent so
    # the failure reaches you instead of the scan going quiet.
    if not shown and any(line.startswith("✓") for line in status):
        out += ["", '{"wakeAgent": false}']
    return "\n".join(out)


def parse_rings(value: str) -> set[int]:
    rings = {int(x) for x in value.split(",") if x.strip()}
    if not rings <= set(RING_NAMES):
        raise argparse.ArgumentTypeError("rings are 0-3, e.g. 0,1")
    return rings


def main(default_rings: str = "0,1") -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rings", type=parse_rings, default=parse_rings(default_rings),
                        help="comma-separated rings: 0 Trier, 1 region, 2 Germany, 3 Europe")
    parser.add_argument("--dry-run", action="store_true", help="don't mark jobs as seen")
    args = parser.parse_args()
    print(run(args.rings, args.dry_run))


if __name__ == "__main__":
    main()
