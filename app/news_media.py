"""Article image previews: bounded public HTTPS reads and an app-owned local cache."""
from __future__ import annotations

import base64
import concurrent.futures
import hashlib
from html.parser import HTMLParser
import http.client
import ipaddress
import json
from pathlib import Path
import re
import socket
import ssl
import threading
import time
import urllib.parse

UA = 'Atlas/1.4 (+https://github.com/Vector1239/atlas)'
MAX_IMAGE = 4 * 1024 * 1024
MAX_HTML = 1024 * 1024


def public_target(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Only public HTTPS preview sources are supported.')
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError('Private addresses are not preview sources.')
    return parsed, sorted(addresses, key=lambda row: row[0] != socket.AF_INET)[0][4][0]


class PublicHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host, timeout=6)
        self.address = address

    def connect(self):
        # Connect to the checked IP while validating TLS against the original hostname.
        self.sock = socket.create_connection((self.address, 443), self.timeout)
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


def fetch_public(url, limit, image=False):
    for _ in range(5):
        parsed, address = public_target(url)
        connection = PublicHTTPSConnection(parsed.hostname, address)
        try:
            path = urllib.parse.urlunsplit(('', '', parsed.path or '/', parsed.query, ''))
            connection.request('GET', path, headers={'User-Agent': UA, 'Accept': 'image/avif,image/webp,image/*' if image else 'text/html', 'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                url = urllib.parse.urljoin(url, response.getheader('Location', ''))
                continue
            if response.status != 200:
                raise ValueError(f'Preview unavailable ({response.status}).')
            mime = response.getheader('Content-Type', '').split(';')[0].lower()
            if (image and mime not in ('image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/avif')) or (not image and mime not in ('text/html', 'application/xhtml+xml')):
                raise ValueError('Unsupported preview format.')
            length = response.getheader('Content-Length')
            if length and int(length) > limit:
                raise ValueError('Preview is too large.')
            body = response.read(limit + 1)
            if len(body) > limit:
                raise ValueError('Preview is too large.')
            return body, mime, url
        finally:
            connection.close()
    raise ValueError('Too many preview redirects.')


class ArticleMetadata(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.values = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta':
            key = (attrs.get('property') or attrs.get('name') or '').lower()
            if key in ('og:image', 'og:image:secure_url', 'og:image:alt', 'twitter:image', 'twitter:image:alt') and attrs.get('content'):
                self.values.setdefault(key, attrs['content'])


def image_metadata(html, page_url):
    parser = ArticleMetadata()
    parser.feed(html)
    values = parser.values
    image = values.get('og:image:secure_url') or values.get('og:image') or values.get('twitter:image')
    if not image:
        return None
    url = urllib.parse.urljoin(page_url, image)
    if re.search(r'(?:^|[/_.-])(?:logo|placeholder|default|favicon)(?:[/_.-]|$)', urllib.parse.urlsplit(url).path, re.I):
        return None
    return {'url': url, 'alt': values.get('og:image:alt') or values.get('twitter:image:alt') or ''}


def article_url(item):
    url = item.get('article_url') or item['url']
    host = urllib.parse.urlsplit(url).hostname or ''
    if host == 'news.google.com':
        # Legacy RSS links sometimes contain a publisher URL. Opaque links remain
        # unillustrated: a Google logo or an unrelated photo isn't an article image.
        try:
            encoded = urllib.parse.urlsplit(url).path.rsplit('/', 1)[-1]
            raw = base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4))
            match = re.search(rb'https://[^\s\x00-\x20\x7f-\xff]+', raw)
            return match.group().decode() if match else None
        except (ValueError, UnicodeError):
            return None
    return url


def image_signature(body, mime):
    if len(body) < 512:
        return False
    return ((mime == 'image/jpeg' and body.startswith(b'\xff\xd8\xff')) or
            (mime == 'image/png' and body.startswith(b'\x89PNG\r\n\x1a\n')) or
            (mime == 'image/gif' and body[:6] in (b'GIF87a', b'GIF89a')) or
            (mime == 'image/webp' and body.startswith(b'RIFF') and body[8:12] == b'WEBP') or
            (mime == 'image/avif' and body[4:8] == b'ftyp' and b'avif' in body[8:32]))


class NewsMedia:
    def __init__(self, state_dir):
        self.folder = Path(state_dir) / 'news_images'
        self.index_file = Path(state_dir) / 'news_media.json'
        self.folder.mkdir(parents=True, exist_ok=True)
        try:
            self.index = json.loads(self.index_file.read_text())
            if not isinstance(self.index, dict):
                self.index = {}
            self.index = {url: row for url, row in self.index.items() if isinstance(row, dict)}
        except (OSError, ValueError):
            self.index = {}
        self.lock = threading.RLock()
        self.status = {'running': False, 'completed': 0, 'total': 0}

    def enrich(self, items):
        with self.lock:
            enriched = []
            for item in items:
                row = self.index.get(item.get('url', ''), {})
                key = row.get('key', '')
                picture = None
                if re.fullmatch(r'[a-f0-9]{64}', key) and (self.folder / key).is_file():
                    picture = {'url': '/api/news/images/' + key, 'alt': row.get('alt', ''),
                               'credit': row.get('credit', ''), 'source_url': row.get('source_url', item.get('url', ''))}
                enriched.append({**item, 'picture': picture})
            return enriched, self.status.copy()

    def image(self, key):
        if not re.fullmatch(r'[a-f0-9]{64}', key):
            return None
        with self.lock:
            mime = next((row['mime'] for row in self.index.values() if row.get('key') == key and row.get('mime')), None)
        path = self.folder / key
        return (path.read_bytes(), mime) if mime and path.is_file() else None

    def _load(self, item):
        try:
            target = article_url(item)
            image = {'url': item['image'], 'alt': item.get('image_alt', '')} if item.get('image') else None
            if not image:
                if not target:
                    return {}
                body, _, target = fetch_public(target, MAX_HTML)
                image = image_metadata(body.decode('utf-8', errors='replace'), target)
            if not image:
                return {}
            source = urllib.parse.urljoin(target or item['url'], image['url'])
            # Some feeds still publish HTTP URLs for images available over HTTPS.
            if source.startswith('http://'):
                source = 'https://' + source[7:]
            body, mime, _ = fetch_public(source, MAX_IMAGE, image=True)
            if not image_signature(body, mime):
                return {}
            key = hashlib.sha256(body).hexdigest()
            temp = self.folder / (key + '.tmp')
            with self.lock:
                if not (self.folder / key).exists():
                    temp.write_bytes(body)
                    temp.replace(self.folder / key)
            return {'key': key, 'mime': mime, 'alt': image.get('alt', '')[:500],
                    'credit': item.get('source', ''), 'source_url': target or item['url']}
        except (OSError, ValueError, http.client.HTTPException):
            return {}

    def start(self, items):
        with self.lock:
            if self.status['running']:
                return
            pending = []
            for item in items[:100]:
                if not item.get('url'):
                    continue
                row = self.index.get(item['url'], {})
                ttl = 7 * 86400 if row.get('key') and (self.folder / row['key']).is_file() else 15 * 60
                if time.time() - row.get('checked_at', 0) > ttl or row.get('feed_image') != item.get('image'):
                    pending.append(dict(item))
            if not pending:
                return
            self.status.update(running=True, completed=0, total=len(pending))
        def worker():
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                    futures = {pool.submit(self._load, item): item for item in pending}
                    for future in concurrent.futures.as_completed(futures):
                        item = futures[future]
                        try:
                            result = future.result()
                        except Exception:
                            result = {}
                        with self.lock:
                            self.index[item['url']] = {**result, 'checked_at': time.time(), 'feed_image': item.get('image')}
                            self.status['completed'] += 1
                with self.lock:
                    self.index = dict(sorted(self.index.items(), key=lambda pair: pair[1].get('checked_at', 0), reverse=True)[:160])
                    keep = {row.get('key') for row in self.index.values()}
                    for path in self.folder.iterdir():
                        if path.name not in keep:
                            path.unlink(missing_ok=True)
                    temporary = self.index_file.with_suffix('.tmp')
                    temporary.write_text(json.dumps(self.index))
                    temporary.replace(self.index_file)
            finally:
                with self.lock:
                    self.status['running'] = False
        threading.Thread(target=worker, daemon=True).start()
