"""Shared helpers for the Germany-life scripts.

Standard library only, so every script runs under Hermes' own Python when a
cron job fires, with nothing extra to install. TOML parsing needs Python 3.11+
(or the `tomli` package); everything else also works on older Pythons.
"""
from __future__ import annotations

import contextlib
import csv
import datetime as dt
import hashlib
import html
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

USER_AGENT = "germany-life-hermes/0.1 (personal news and job digest)"
POINTER = Path(__file__).with_name("germany_life_home.txt")
WORKDAY_LIMIT = 140  # full days per calendar year on a student residence permit (§16b AufenthG)


# ---------------------------------------------------------------- paths

def project_home() -> Path:
    """The project folder: $GERMANY_LIFE_HOME, else the pointer file written by
    install.sh, else the checkout this file lives in."""
    env = os.environ.get("GERMANY_LIFE_HOME")
    if env:
        return Path(env).expanduser()
    if POINTER.exists():
        return Path(POINTER.read_text(encoding="utf-8").strip()).expanduser()
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    return project_home() / "data"


def state_dir() -> Path:
    path = project_home() / "state"
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------- config

def _toml():
    try:
        import tomllib
        return tomllib
    except ModuleNotFoundError:
        try:
            import tomli
            return tomli
        except ModuleNotFoundError:
            sys.exit("Reading the TOML config needs Python 3.11+. Run this through ./gl, "
                     "which finds a suitable Python, or set GL_PYTHON.")


def load_config() -> dict:
    path = project_home() / "config" / "sources.toml"
    if not path.exists():
        return {}
    return _toml().loads(path.read_text(encoding="utf-8"))


def read_profile() -> str:
    path = project_home() / "profile.md"
    if not path.exists():
        return "(profile.md is missing: copy templates/profile.md to profile.md and fill it in)"
    return path.read_text(encoding="utf-8").strip()


def local_tz(cfg: dict | None = None):
    name = ((cfg or {}).get("home") or {}).get("timezone", "Europe/Berlin")
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        return None


def now(cfg: dict | None = None) -> dt.datetime:
    tz = local_tz(cfg)
    return dt.datetime.now(tz) if tz else dt.datetime.now().astimezone()


# ---------------------------------------------------------------- state files

def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


@contextlib.contextmanager
def file_lock(path: Path):
    """Hold an exclusive lock for a read-modify-write of `path`. The Atlas app and the
    Hermes cron jobs are separate processes that update the same files."""
    import fcntl
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_suffix(path.suffix + ".lock"), "a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def save_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------- http

_SSL_CONTEXT = None


def _ssl_context() -> ssl.SSLContext:
    # Some standalone Pythons on macOS have no system CA bundle; certifi ships with
    # Hermes, so prefer it unless the environment already points at a bundle.
    if os.environ.get("SSL_CERT_FILE"):
        return ssl.create_default_context()
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def http_get(url: str, headers: dict | None = None, timeout: int = 20) -> bytes:
    global _SSL_CONTEXT
    if _SSL_CONTEXT is None:
        _SSL_CONTEXT = _ssl_context()
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "*/*", **(headers or {})})
    with urllib.request.urlopen(request, timeout=timeout, context=_SSL_CONTEXT) as response:
        return response.read(5_000_000)


def http_json(url: str, headers: dict | None = None, timeout: int = 20):
    return json.loads(http_get(url, headers, timeout).decode("utf-8"))


def short_error(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    if isinstance(exc, urllib.error.URLError):
        return f"network error ({exc.reason})"
    return f"{type(exc).__name__}: {exc}"[:120]


# ---------------------------------------------------------------- text

_TAG = re.compile(r"<[^>]+>")
_INVISIBLE = re.compile("[​-‏‪-‮⁠-⁤﻿]")


def clean_text(value: str | None, limit: int | None = None) -> str:
    text = _TAG.sub(" ", value or "")
    text = _TAG.sub(" ", html.unescape(text))
    text = _INVISIBLE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9äöüß]+", " ", (value or "").lower()).strip()


def short_id(key: str, prefix: str = "J") -> str:
    return f"{prefix}-{hashlib.sha1(key.encode('utf-8')).hexdigest()[:5]}"


_EN_WORDS = {"the", "and", "you", "with", "for", "our", "are", "will", "your", "we", "of", "to", "in"}
_DE_WORDS = {"und", "der", "die", "das", "mit", "für", "wir", "sie", "ihre", "eine", "von", "zu", "bei"}


def looks_english(text: str) -> bool | None:
    words = re.findall(r"[a-zäöüß]+", (text or "").lower())
    if len(words) < 25:
        return None
    en = sum(w in _EN_WORDS for w in words)
    de = sum(w in _DE_WORDS for w in words)
    return en > de * 1.5


# ---------------------------------------------------------------- feeds

def parse_date(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    value = value.strip()
    parsed = None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        pass
    if parsed is None:
        try:
            parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_feed(data: bytes) -> list[dict]:
    """Items from an RSS 2.0, RSS 1.0 (RDF) or Atom feed."""
    root = ET.fromstring(data)
    items = []
    for element in root.iter():
        if _local_name(element.tag) not in ("item", "entry"):
            continue
        item = {"title": "", "link": "", "published": None, "source": "", "summary": ""}
        for child in element:
            name = _local_name(child.tag)
            text = (child.text or "").strip()
            if name == "title":
                item["title"] = clean_text(text)
            elif name == "link":
                href = child.attrib.get("href")
                if href and child.attrib.get("rel", "alternate") == "alternate" and not item["link"]:
                    item["link"] = href
                elif text and not item["link"]:
                    item["link"] = text
            elif name in ("pubDate", "published", "updated", "date") and item["published"] is None:
                item["published"] = parse_date(text)
            elif name == "source":
                item["source"] = clean_text(text)
            elif name in ("description", "summary", "content", "encoded") and not item["summary"]:
                item["summary"] = clean_text(text, 220)
        if item["title"]:
            items.append(item)
    return items


# ---------------------------------------------------------------- deadlines

def load_deadlines(include_examples: bool = False) -> list[dict]:
    path = data_dir() / "deadlines.toml"
    if not path.exists():
        return []
    entries = _toml().loads(path.read_text(encoding="utf-8")).get("deadline", [])
    result = []
    for entry in entries:
        if entry.get("example") and not include_examples:
            continue
        date = entry.get("date")
        if isinstance(date, dt.datetime):
            date = date.date()
        elif isinstance(date, str):
            date = dt.date.fromisoformat(date)
        if not isinstance(date, dt.date):
            continue
        result.append({**entry, "date": date})
    return sorted(result, key=lambda e: e["date"])


# ---------------------------------------------------------------- work days

def workdays_summary(year: int) -> dict | None:
    """Count days against the student work limit for one calendar year.

    A day with more than 4 hours of regular work is a full day, up to 4 hours is a
    half day. Rows with kind "hiwi" (student assistant at the university) are
    listed separately because they do not count against the limit.
    """
    path = data_dir() / "worklog.csv"
    if not path.exists():
        return None
    hours_by_day: dict[dt.date, float] = {}
    hiwi_days = set()
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                day = dt.date.fromisoformat((row.get("date") or "").strip())
                hours = float(row.get("hours") or 0)
            except ValueError:
                continue
            if day.year != year or hours <= 0:
                continue
            if (row.get("kind") or "regular").strip().lower() == "hiwi":
                hiwi_days.add(day)
                continue
            hours_by_day[day] = hours_by_day.get(day, 0.0) + hours
    full = sum(1 for h in hours_by_day.values() if h > 4)
    half = sum(1 for h in hours_by_day.values() if h <= 4)
    used = full + half / 2
    return {"year": year, "full": full, "half": half, "used": used,
            "remaining": WORKDAY_LIMIT - used, "hiwi_days": len(hiwi_days)}


def workdays_line(summary: dict | None) -> str:
    if summary is None:
        return "No work log yet (data/worklog.csv)."
    return (f"{summary['year']}: {summary['used']:g} of {WORKDAY_LIMIT} full-day equivalents used "
            f"({summary['full']} full + {summary['half']} half days), {summary['remaining']:g} left. "
            f"HiWi days not counted: {summary['hiwi_days']}.")
