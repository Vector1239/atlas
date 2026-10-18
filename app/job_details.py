"""Read source-provided job descriptions on demand, without an AI model."""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
import threading
import time

import gl_common as gl
import job_providers
import news_media

LOCK = threading.Lock()
NOISE = {"script", "style", "noscript", "template", "nav", "header", "footer", "aside", "form", "iframe", "button", "svg"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class PostingHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.structured = [], []
        self.parts = {"main": [], "article": [], "body": []}
        self.script = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "script" and values.get("type", "").lower() == "application/ld+json":
            self.script = []
        if tag not in VOID:
            self.stack.append((tag, "main" if values.get("role") == "main" else tag))
        if tag in {"p", "div", "li", "br", "h1", "h2", "h3", "section"}:
            self.handle_data("\n")

    def handle_endtag(self, tag):
        if tag == "script" and self.script is not None:
            try:
                self.structured.append(json.loads("".join(self.script)))
            except (ValueError, RecursionError):
                pass
            self.script = None
        # The stack only selects readable regions; an unmatched close is harmless.
        tags = [entry[0] for entry in self.stack]
        if tag in tags:
            self.stack = self.stack[:len(tags) - 1 - tags[::-1].index(tag)]
        self.handle_data("\n")

    def handle_data(self, data):
        if self.script is not None:
            self.script.append(data)
        if any(tag in NOISE for tag, _ in self.stack):
            return
        for region in self.parts:
            if any(scope == region for _, scope in self.stack):
                self.parts[region].append(data)


def posting_text(html):
    parser = PostingHTML()
    parser.feed(html)
    pending = list(parser.structured)
    for _ in range(1000):
        if not pending:
            break
        node = pending.pop(0)
        if isinstance(node, list):
            pending.extend(node)
        elif isinstance(node, dict):
            kinds = node.get("@type", [])
            if kinds == "JobPosting" or isinstance(kinds, list) and "JobPosting" in kinds:
                description = node.get("description")
                if isinstance(description, str):
                    text = gl.clean_text(description, 30000)
                    if len(text) >= 80:
                        return text, "JobPosting structured data"
            if "@graph" in node:
                pending.append(node["@graph"])
    for region in ("main", "article", "body"):
        text = gl.clean_text(" ".join(parser.parts[region]), 30000)
        if len(text) >= 120:
            return text, "Listing page"
    return "", ""


def load(job, state_dir):
    if job.get("text"):
        return {"text": job["text"], "detail_source": job.get("detail_source", job["source"])}
    path = state_dir / "job_details.json"
    key = hashlib.sha256(f"{job['source']}:{job['source_id']}:{job['url']}".encode()).hexdigest()
    with LOCK, gl.file_lock(path):
        now = time.time()
        cache = gl.load_json(path, {})
        cached = cache.get(key, {})
        if now - cached.get("at", 0) < (7 * 86400 if cached.get("text") else 900):
            return {k: v for k, v in cached.items() if k != "at"}
        text, source = "", ""
        if job["source"] == "Bundesagentur":
            try:
                text = job_providers.bundesagentur_description(job["source_id"])
                source = "Bundesagentur job details"
            except Exception:
                pass
        if not text:
            try:
                body, _, _ = news_media.fetch_public(job["url"], 1024 * 1024)
                text, source = posting_text(body.decode("utf-8", errors="replace"))
            except Exception:
                pass
        result = {"text": text, "detail_source": source if text else "",
                  "detail_error": "" if text else "The source did not provide readable details. Open the original listing for requirements."}
        cache = {k: v for k, v in cache.items() if now - v.get("at", 0) < 7 * 86400}
        cache[key] = {**result, "at": now}
        gl.save_json(path, dict(sorted(cache.items(), key=lambda row: row[1]["at"], reverse=True)[:500]))
        return result
