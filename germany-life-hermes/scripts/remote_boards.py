"""Free remote-job boards: Remotive, Remote OK, Jobicy and Himalayas (public JSON, no key).

Their terms ask for a link back to the listing on their site and their name as the source;
every job keeps the board's own URL and source name. Remotive asks for at most 4 requests a
day, Jobicy for at most one sync an hour and Himalayas refreshes daily, so each request is
cached for 24 hours. Known location restrictions must include Germany or a broader region:
a US company hiring worldwide counts, a "USA only" role does not. Missing Remote OK
locations remain explicitly unconfirmed.
"""
from __future__ import annotations

import datetime as dt
import re
import time
import urllib.parse

import gl_common as gl
from job_providers import safe_link

CACHE_SECONDS = 24 * 3600
ELIGIBLE = re.compile(r"worldwide|anywhere|global|europe|\beu\b|emea|germany|deutschland|\bdach\b|\bcet\b|cest|central europe", re.I)
GERMANY = re.compile(r"germany|deutschland|\bdach\b", re.I)
PERIODS = {"hour": "HOUR", "hourly": "HOUR", "month": "MONTH", "monthly": "MONTH", "year": "YEAR", "yearly": "YEAR", "annual": "YEAR"}
DEFAULTS = {"enabled": True, "remotive_categories": ["data", "software-dev"],
            "jobicy_industries": ["data-science", "engineering"], "jobicy_geos": ["europe", "anywhere"],
            "himalayas_queries": ["data scientist", "data analyst", "data engineer", "machine learning", "ai engineer",
                                  "software engineer", "full stack", "frontend", "backend", "mobile developer"],
            "himalayas_country": "DE"}


def _cached(url):
    """Share a daily cache with the app; back off failures and reuse saved data."""
    path = gl.state_dir() / "remote_boards_cache.json"
    with gl.file_lock(path):
        cache = gl.load_json(path, {})
        entry = cache.get(url, {})
        now = time.time()
        if now - entry.get("at", 0) < CACHE_SECONDS:
            return entry["data"], True
        if entry.get("retry_at", 0) > now:
            if "data" in entry:
                return entry["data"], True
            raise ValueError("Remote source temporarily unavailable; retry after one hour.")
        try:
            data = gl.http_json(url, timeout=15)
            rows = data if isinstance(data, list) else data.get("jobs") if isinstance(data, dict) else None
            if not isinstance(rows, list):
                raise ValueError("Unexpected jobs response")
        except Exception:
            cache[url] = {**entry, "retry_at": now + 3600}
            gl.save_json(path, cache)
            if "data" in entry:
                return entry["data"], True
            raise
        cache = {k: v for k, v in cache.items() if now - v.get("at", 0) < 30 * CACHE_SECONDS}
        cache[url] = {"at": now, "data": data}
        gl.save_json(path, cache)
    return data, False


def remote_date(value):
    """Accept ISO dates and the second/millisecond epochs used by job feeds."""
    try:
        if isinstance(value, (int, float)):
            return dt.datetime.fromtimestamp(value / 1000 if value > 1e11 else value, dt.timezone.utc).isoformat()
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat() if isinstance(value, str) and value else ""
    except (ValueError, OverflowError, OSError):
        return ""


def remoteok(item):
    if not isinstance(item, dict) or not item.get("id") or not isinstance(item.get("position"), str) or not item["position"].strip():
        return None
    link = safe_link(item.get("url"))
    if not link:
        return None
    # An omitted location isn't proof of worldwide eligibility.
    return _job("Remote OK", item["id"], item["position"], item.get("company", ""),
                item.get("location") or "Location not specified", remote_date(item.get("date") or item.get("epoch")),
                link, item.get("description", ""), region_name=item.get("location") or "Location not specified")


def _job(source, source_id, title, company, scope, posted, url, text, **extra):
    scope = gl.clean_text(scope or "", 120)
    return {"source": source, "source_id": str(source_id), "ring": 2 if GERMANY.search(scope) else 3,
            "title": gl.clean_text(title, 500), "company": gl.clean_text(company, 300),
            "where": f"Remote · {scope or 'location not stated'}", "city": "Remote", "region_name": "", "country": "",
            "posted": (posted or "")[:10], "url": url, "text": gl.clean_text(text, 4000), "remote": True, "visa": False,
            "remote_scope": scope, **extra}


def remotive(item):
    if not isinstance(item, dict) or not item.get("id") or not item.get("title"):
        return None
    salary = gl.clean_text(item.get("salary") or "", 80)
    return _job("Remotive", item["id"], item["title"], item.get("company_name", ""), item.get("candidate_required_location"),
                item.get("publication_date"), item.get("url", ""),
                (f"Salary: {salary}. " if salary else "") + (item.get("description") or ""),
                job_types=[gl.clean_text(item.get("job_type") or "", 40)] if item.get("job_type") else [],
                tags=[gl.clean_text(item.get("category") or "", 60)] if item.get("category") else [])


def jobicy(item):
    if not isinstance(item, dict) or not item.get("id") or not item.get("jobTitle"):
        return None
    salary = {}
    low, high = item.get("salaryMin"), item.get("salaryMax") or item.get("annualSalaryMax")
    low = low if low is not None else item.get("annualSalaryMin")
    period = PERIODS.get(str(item.get("salaryPeriod") or ("yearly" if item.get("annualSalaryMin") else "")).lower())
    if period and any(isinstance(v, (int, float)) and v > 0 for v in (low, high)):
        salary = {"min": low if isinstance(low, (int, float)) else None, "max": high if isinstance(high, (int, float)) else None,
                  "currency": str(item.get("salaryCurrency") or "")[:3].upper(), "period": period}
    listed = lambda name: [gl.clean_text(v, 60) for v in (item.get(name) or [])[:6] if isinstance(v, str)] \
        if isinstance(item.get(name), list) else [gl.clean_text(str(item.get(name)), 60)] if item.get(name) else []
    return _job("Jobicy", item["id"], item["jobTitle"], item.get("companyName", ""), item.get("jobGeo"), item.get("pubDate"),
                item.get("url", ""), item.get("jobDescription") or item.get("jobExcerpt") or "",
                salary=salary, job_types=listed("jobType"), tags=listed("jobIndustry"))


def himalayas(item):
    if not isinstance(item, dict) or not isinstance(item.get("guid"), str) or not item.get("title"):
        return None
    expiry = remote_date(item.get("expiryDate"))
    if expiry and expiry[:10] < dt.datetime.now(dt.timezone.utc).date().isoformat():
        return None
    posted = remote_date(item.get("pubDate"))
    salary = {}
    period = PERIODS.get(str(item.get("salaryPeriod") or "annual").lower())
    low, high = item.get("minSalary"), item.get("maxSalary")
    if period and any(isinstance(v, (int, float)) and v > 0 for v in (low, high)):
        salary = {"min": low if isinstance(low, (int, float)) else None, "max": high if isinstance(high, (int, float)) else None,
                  "currency": str(item.get("currency") or "")[:3].upper(), "period": period}
    # No location restriction means the role is open worldwide.
    places = [gl.clean_text(p if isinstance(p, str) else p.get("name", ""), 60)
              for p in item.get("locationRestrictions") or [] if isinstance(p, (str, dict))]
    scope = ", ".join(places[:8]) or "Worldwide"
    zones = item.get("timezoneRestrictions") or []
    zone_note = " · Timezones: " + ", ".join(str(z) for z in zones) if zones else ""
    words = lambda name: [gl.clean_text(v, 60) for v in item.get(name) or [] if isinstance(v, str)][:6]
    return _job("Himalayas", item["guid"], item["title"], item.get("companyName", ""), scope,
                posted, item["guid"] if safe_link(item["guid"]) else item.get("applicationLink", ""),
                item.get("description") or item.get("excerpt") or "", salary=salary,
                job_types=[gl.clean_text(item["employmentType"], 40)] if isinstance(item.get("employmentType"), str) else [],
                tags=words("categories") + words("parentCategories"), region_name=scope + zone_note)


def fetch_remote(cfg, rings, matcher, status):
    options = {**DEFAULTS, **cfg.get("jobs", {}).get("remote", {})}
    if not options.get("enabled", True) or not rings & {2, 3}:
        return []
    requests = [("Remotive", "https://remotive.com/api/remote-jobs?" + urllib.parse.urlencode({"category": c}),
                 lambda data: data.get("jobs") or [], remotive) for c in options["remotive_categories"]]
    requests += [("Jobicy", "https://jobicy.com/api/v2/remote-jobs?" + urllib.parse.urlencode({"count": 100, "geo": geo, "industry": industry}),
                  lambda data: data.get("jobs") or [], jobicy)
                 for industry in options["jobicy_industries"] for geo in options["jobicy_geos"]]
    # Himalayas' country filter already includes roles open worldwide.
    requests += [("Himalayas", "https://himalayas.app/jobs/api/search?" + urllib.parse.urlencode(
                      {"q": query, "country": options["himalayas_country"], "sort": "recent"}),
                  lambda data: data.get("jobs") or [], himalayas) for query in options["himalayas_queries"]]
    if options.get("remoteok", True):
        requests.append(("Remote OK", "https://remoteok.com/api", lambda data: data, remoteok))
    cutoff = (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=cfg.get("jobs", {}).get("max_age_days", 14))).isoformat()
    found, seen, counts, errors, outside = [], set(), {}, [], 0
    for board, url, rows, normalize in requests:
        counts.setdefault(board, 0)
        try:
            data, _ = _cached(url)
        except Exception as exc:
            errors.append(f"{board}: {gl.short_error(exc)}")
            continue
        for item in rows(data) if isinstance(data, (dict, list)) else []:
            job = normalize(item)
            if not job or not safe_link(job["url"]):
                continue
            key = f"{job['source']}:{job['source_id']}"
            if key in seen or job["ring"] not in rings or (job["posted"] and job["posted"] < cutoff):
                continue
            if not matcher.relevant(job["title"], " ".join(job.get("tags", []))):
                continue
            if job["remote_scope"] and job["remote_scope"] != "Location not specified" and not ELIGIBLE.search(job["remote_scope"]):
                outside += 1
                continue
            seen.add(key)
            counts[board] += 1
            found.append(job)
    mark = "✗" if len(errors) == len(requests) else "✓"
    status.append(f"{mark} Remote boards: " + ", ".join(f"{board} {count}" for board, count in counts.items())
                  + f" matching remote roles you can do from Germany; {outside} that hire only elsewhere (e.g. USA only) skipped"
                  + (f"; {len(errors)} unavailable ({errors[0]})" if errors else ""))
    return found
