"""Optional JSearch access and Bundesagentur descriptions, using public provider protocols.

Dossier's provider choices informed this integration; this is an independent,
standard-library implementation for Atlas and its Hermes scripts.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse

import gl_common as gl

HOSTS = {
    "openwebninja": "https://api.openwebninja.com/jsearch/search-v2",
    "rapidapi": "https://jsearch.p.rapidapi.com/search",
}
MONTHLY_LIMIT = 180  # Leave headroom below the provider's 200-request free plan.
CACHE_SECONDS = 24 * 3600


def credentials():
    path = gl.state_dir() / "job_credentials.json"
    saved = gl.load_json(path, None)
    if isinstance(saved, dict):
        return saved.get("host", "openwebninja"), saved.get("key", "")
    return os.environ.get("JSEARCH_HOST", "openwebninja"), os.environ.get("JSEARCH_API_KEY", "")


def save_credentials(host, key):
    if host not in HOSTS or not isinstance(key, str) or len(key) > 1000 or any(c.isspace() for c in key):
        raise ValueError("Choose a JSearch provider and enter a valid API key.")
    path = gl.state_dir() / "job_credentials.json"
    with gl.file_lock(path):
        tmp = path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump({"host": host, "key": key}, handle)
        os.replace(tmp, path)


def provider_state():
    host, key = credentials()
    usage = gl.load_json(gl.state_dir() / "jsearch_cache.json", {})
    month = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m")
    return {"host": host if host in HOSTS else "openwebninja", "configured": bool(key),
            "requests": usage.get("requests", 0) if usage.get("month") == month else 0,
            "monthly_limit": MONTHLY_LIMIT}


def safe_link(value):
    if not isinstance(value, str):
        return ""
    try:
        url = urllib.parse.urlsplit(value)
        return value if url.scheme in ("http", "https") and url.hostname and not url.username and not url.password else ""
    except ValueError:
        return ""


def normalize_jsearch(item, ring):
    if not isinstance(item, dict) or not isinstance(item.get("job_id"), str) or not item["job_id"]:
        return None
    text = lambda name: item.get(name) if isinstance(item.get(name), str) else ""
    options = item.get("apply_options") if isinstance(item.get("apply_options"), list) else []
    links = [o.get("apply_link") for o in options if isinstance(o, dict) and o.get("is_direct") is True]
    links += [text("job_apply_link")] + [o.get("apply_link") for o in options if isinstance(o, dict)] + [text("job_google_link")]
    link = next((safe_link(url) for url in links if safe_link(url)), "")
    if not link or not text("job_title").strip():
        return None
    place = text("job_location").split("•")[0].strip()
    city = text("job_city") or place.split(",")[0].strip()
    place = place or ", ".join(filter(None, [city, text("job_state"), text("job_country")]))
    posted = text("job_posted_at_datetime_utc")
    if not posted and isinstance(item.get("job_posted_at_timestamp"), (int, float)):
        try:
            posted = dt.datetime.fromtimestamp(item["job_posted_at_timestamp"], dt.timezone.utc).isoformat()
        except (OverflowError, ValueError, OSError):
            pass
    return {"source": "JSearch", "source_id": item["job_id"], "ring": ring,
            "title": gl.clean_text(text("job_title"), 500), "company": gl.clean_text(text("employer_name"), 300),
            "where": gl.clean_text(place) or "?", "city": gl.clean_text(city), "country": text("job_country"),
            "region_name": text("job_state"), "posted": posted[:10], "url": link,
            "text": gl.clean_text(text("job_description"), 30000), "via": gl.clean_text(text("job_publisher")),
            "remote": item.get("job_is_remote") is True, "visa": False}


def search_url(search, host, max_age):
    place = search.get("where", "")
    params = {"query": search["what"] + (f" in {place}" if place else ""),
              "country": search.get("country", "de"), "date_posted": "month" if max_age > 7 else "week"}
    if place and "radius_km" in search:
        params["radius"] = search["radius_km"]
    if search.get("language"):
        params["language"] = search["language"]
    if host == "rapidapi":
        params.update(page=1, num_pages=1)
    return HOSTS[host] + "?" + urllib.parse.urlencode(params)


def cached_jsearch(search, host, max_age):
    """Read saved results without reserving a request or contacting the provider."""
    cache_key = hashlib.sha256(search_url(search, host, max_age).encode()).hexdigest()
    state = gl.load_json(gl.state_dir() / "jsearch_cache.json", {})
    entry = state.get("queries", {}).get(cache_key, {})
    rows = entry.get("jobs", [])
    return (rows, True) if isinstance(rows, list) and time.time() - entry.get("at", 0) < 30 * CACHE_SECONDS else ([], False)


def search_jsearch(search, key, host, max_age):
    """One page per query/day; share cache and a hard request budget with cron.

    Reserve a request before sending it, including failures. No retries, automatic
    pagination or paid-plan upgrades; provider authentication/quota errors back off.
    """
    url = search_url(search, host, max_age)
    cache_key = hashlib.sha256(url.encode()).hexdigest()
    fingerprint = hashlib.sha256((host + key).encode()).hexdigest()
    path = gl.state_dir() / "jsearch_cache.json"
    with gl.file_lock(path):
        now = time.time()
        month = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m")
        state = gl.load_json(path, {})
        if state.get("month") != month:
            state.update(month=month, requests=0)
        entries = state.setdefault("queries", {})
        state["queries"] = entries = {k: v for k, v in entries.items() if now - v.get("at", 0) < 30 * CACHE_SECONDS}
        cached = entries.get(cache_key, {})
        if now - cached.get("at", 0) < CACHE_SECONDS:
            return cached["jobs"], True
        if state.get("blocked_key") == fingerprint and state.get("blocked_until", 0) > now:
            if cached:
                return cached["jobs"], True
            raise ValueError("JSearch is paused after a provider error; try again tomorrow or replace the key.")
        if state.get("requests", 0) >= MONTHLY_LIMIT:
            if cached:
                return cached["jobs"], True
            raise ValueError("Atlas's monthly JSearch request limit is reached; cached listings remain available.")
        headers = {"x-api-key": key} if host == "openwebninja" else {"x-rapidapi-key": key, "x-rapidapi-host": "jsearch.p.rapidapi.com"}
        state["requests"] = state.get("requests", 0) + 1
        gl.save_json(path, state)
        try:
            payload = gl.http_json(url, headers=headers)
            data = payload.get("data") if isinstance(payload, dict) else None
            raw = data.get("jobs") if isinstance(data, dict) else data
            if not isinstance(raw, list):
                raise ValueError("JSearch returned an unexpected response.")
        except Exception as exc:
            state.update(blocked_key=fingerprint, blocked_until=now + (CACHE_SECONDS if isinstance(exc, urllib.error.HTTPError) and exc.code in (401, 403, 429) else 900))
            gl.save_json(path, state)
            raise ValueError(f"JSearch request failed ({gl.short_error(exc)}).") from None
        entries[cache_key] = {"at": now, "jobs": raw}
        gl.save_json(path, state)
        return raw, False


def fetch_jsearch(cfg, rings, matcher, status, *, allow_network=False):
    """Automatic callers read cache only, even when it expires or config enables JSearch.

    allow_network is reserved for the app's explicit manual search action. The
    legacy enabled flag stays false to protect older app and cron installations.
    """
    options = cfg.get("jobs", {}).get("jsearch", {})
    searches = [s for s in options.get("searches", []) if int(s.get("ring", 2)) in rings]
    if not searches:
        return []
    host, key = credentials()
    if not key:
        status.append("· JSearch: optional; add a free API key in Settings → Sources")
        return []
    if host not in HOSTS:
        status.append("✗ JSearch: unsupported provider")
        return []
    found, seen, cached, errors = [], set(), 0, []
    max_age = cfg.get("jobs", {}).get("max_age_days", 14)
    cutoff = (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=max_age)).isoformat()
    for search in searches:
        try:
            rows, hit = (search_jsearch(search, key, host, max_age) if allow_network else
                         cached_jsearch(search, host, max_age))
            cached += hit
        except Exception as exc:
            errors.append(gl.short_error(exc))
            continue
        for item in rows:
            job = normalize_jsearch(item, int(search.get("ring", 2)))
            if not job or job["source_id"] in seen or not matcher.relevant(job["title"]):
                continue
            if job["posted"] and job["posted"] < cutoff:
                continue
            seen.add(job["source_id"])
            found.append(job)
    mark = "✗" if len(errors) == len(searches) else "✓"
    status.append(f"{mark} JSearch: {len(found)} matching postings; {cached} cached searches"
                  + ("; manual requests only, no credits used" if not allow_network else "")
                  + (f"; {len(errors)} unavailable ({errors[0]})" if errors else ""))
    return found


def bundesagentur_description(reference):
    encoded = urllib.parse.quote(base64.b64encode(reference.encode()).decode(), safe="")
    payload = gl.http_json("https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobdetails/" + encoded,
                           headers={"X-API-Key": "jobboerse-jobsuche"}, timeout=10)
    return gl.clean_text(payload.get("stellenangebotsBeschreibung"), 30000)
