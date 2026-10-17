"""Public technology feeds, with explicit dates, provenance and cache fallback."""
import concurrent.futures
import datetime as dt
import hashlib
import functools
import json
from pathlib import Path
import re
import threading
import unicodedata
import urllib.parse

import discovery
import gl_common as gl

CATALOG = json.loads((Path(__file__).parent / 'content/tech.json').read_text())
EUROPE = set('Albania Andorra Austria Belarus Belgium Bosnia Bulgaria Croatia Cyprus Czechia Denmark Estonia Finland France Germany Greece Hungary Iceland Ireland Italy Kosovo Latvia Liechtenstein Lithuania Luxembourg Malta Moldova Monaco Montenegro Netherlands Norway Poland Portugal Romania Russia Serbia Slovakia Slovenia Spain Sweden Switzerland Turkey Ukraine'.split()) | {'United Kingdom', 'Czech Republic', 'North Macedonia', 'Bosnia and Herzegovina', 'The Netherlands', 'Online'}
FEEDS = [
    ('GitHub Blog', 'https://github.blog/feed/'),
    ('Cloudflare Blog', 'https://blog.cloudflare.com/rss/'),
    ('Google Developers Blog', 'https://developers.googleblog.com/feeds/posts/default?alt=rss'),
]
CONFERENCES = 'https://developers.events/all-events.json'
REFRESH_LOCK = threading.Lock()
STATUS = {'running': False, 'error': ''}
BASEMAP = json.loads((Path(__file__).parent / 'content/political-map.json').read_text())


def contains(geometry, lat, lon):
    def ring(points):
        inside = False
        for i, (x, y) in enumerate(points):
            px, py = points[i - 1]
            if (y > lat) != (py > lat) and lon < (px - x) * (lat - y) / (py - y) + x:
                inside = not inside
        return inside
    def polygon(rings):
        return ring(rings[0]) and not any(ring(hole) for hole in rings[1:])
    return polygon(geometry['coordinates']) if geometry['type'] == 'Polygon' else any(polygon(p) for p in geometry['coordinates'])


@functools.lru_cache(maxsize=2000)
def city_location(city, country):
    known = discovery.city_location(city, country)
    if known:
        return known
    aliases = {'München':'Munich', 'Bruxelles':'Brussels', 'Brussel':'Brussels', 'Köln':'Cologne', 'Praha':'Prague', 'Kraków':'Krakow'}
    def key(value):
        return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold()) if not unicodedata.combining(c))
    candidates = [row for row in BASEMAP['cities'] if key(row['name']) == key(aliases.get(city, city or ''))]
    countries = [row for row in BASEMAP['countries']['features'] if row['properties']['name'] == {'The Netherlands':'Netherlands', 'Czech Republic':'Czechia'}.get(country, country)]
    matches = [row for row in candidates if any(contains(c['geometry'], row['lat'], row['lon']) for c in countries)]
    if len(matches) != 1:
        return None
    row = matches[0]
    return {'lat': row['lat'], 'lon': row['lon'], 'label':city, 'country':country, 'source':'Natural Earth · city centre'}


def valid_url(url):
    try:
        parsed = urllib.parse.urlsplit(url)
        return parsed.scheme in ('http', 'https') and bool(parsed.hostname) and not parsed.username
    except ValueError:
        return False


def event_rows(rows, today):
    result = []
    for row in rows:
        if not isinstance(row, dict) or str(row.get('status', '')).casefold() in ('cancelled', 'canceled') or not valid_url(row.get('hyperlink', '')):
            continue
        try:
            dates = row['date']
            start = dt.datetime.fromtimestamp(dates[0] / 1000, dt.timezone.utc).date()
            end = dt.datetime.fromtimestamp(dates[-1] / 1000, dt.timezone.utc).date()
        except (KeyError, ValueError, TypeError, IndexError, OverflowError, OSError):
            continue
        if end < today or end < start:
            continue
        online = bool(re.search(r'\bonline\b|\bvirtual\b', str(row.get('location') or ''), re.I))
        country = str(row.get('country') or '')
        if not online and country not in EUROPE:
            continue
        city = str(row.get('city') or '')
        location = city_location(city, country)
        result.append({'id': hashlib.sha256((row['hyperlink'] + start.isoformat()).encode()).hexdigest()[:16],
                       'title': str(row.get('name') or 'Technology event')[:300], 'kind': 'hackathon' if 'hackathon' in str(row.get('tags', [])).lower() + str(row.get('name') or '').lower() else 'conference',
                       'start': start.isoformat(), 'end': end.isoformat(), 'city': city or 'Location not provided',
                       'country': country, 'online': online, 'location': None if online else location,
                       'venue': row.get('location', ''), 'url': row['hyperlink'], 'source': 'developers.events',
                       'source_url': 'https://developers.events/', 'checked_at': today.isoformat(),
                       'description': 'Community-listed event. Check the organiser’s page for programme, tickets and changes.'})
    return result


def upcoming(rows, today):
    unique = {}
    for row in rows:
        try:
            start = dt.date.fromisoformat(row['start'])
            end = dt.date.fromisoformat(row.get('end') or row['start'])
            checked = dt.date.fromisoformat(row['checked_at'])
        except (KeyError, ValueError, TypeError):
            continue
        if end < today or end < start or row.get('cancelled') or not valid_url(row.get('url', '')):
            continue
        key = (re.sub(r'\W', '', re.sub(r'\b20\d\d\b', '', row['title'].casefold())), row['start'])
        # Organiser-verified records override community records of the same event.
        unique[key] = {**row, 'location': None if row.get('online') else row.get('location') or city_location(row.get('city'), row.get('country', 'Germany')),
                       'stale': (today - checked).days > 14, 'ongoing': start <= today <= end}
    return sorted(unique.values(), key=lambda r: (r['start'], r['title']))


def public_state(state_dir, today):
    cached = gl.load_json(state_dir / 'tech.json', {})
    events = upcoming([*cached.get('events', []), *CATALOG['events']], today)
    bases = {city: {'city':city, **place} for city, place in discovery.PLACES.items()}
    bases.update({row['city']:{'city':row['city'], **row['location']} for row in events if row.get('location')})
    return {'events': events,
            'posts': cached.get('posts', []), 'sources': cached.get('sources', []),
            'calendars': CATALOG['calendars'], 'checked_at': CATALOG['checked_at'],
            'bases': sorted(bases.values(), key=lambda p:p['city']),
            'refreshed_at': cached.get('refreshed_at'), **STATUS}


def refresh(state_dir, today):
    if not REFRESH_LOCK.acquire(blocking=False):
        return
    STATUS.update(running=True, error='')
    try:
        cached = gl.load_json(state_dir / 'tech.json', {})
        sources, posts = [], []
        events = cached.get('events', [])
        def fetch_posts(name, url):
            result = []
            for item in gl.parse_feed(gl.http_get(url)):
                if not valid_url(item.get('link', '')):
                    continue
                published = item.get('published')
                if published and published.date() > today:
                    continue
                result.append({'title': item['title'], 'url': item['link'], 'source': name,
                               'published': published.isoformat() if published else None, 'kind': 'blog'})
                if len(result) == 20:
                    break
            if not result:
                raise ValueError('No readable posts returned')
            return result
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            tasks = {pool.submit(fetch_posts, name, url): name for name, url in FEEDS}
            conference = pool.submit(gl.http_json, CONFERENCES)
            for future, name in tasks.items():
                try:
                    rows = future.result()
                    posts.extend(rows)
                    sources.append({'name': name, 'ok': True, 'detail': f'{len(rows)} recent posts'})
                except Exception as exc:
                    posts.extend(row for row in cached.get('posts', []) if row.get('source') == name)
                    sources.append({'name': name, 'ok': False, 'detail': 'Keeping cached posts. ' + gl.short_error(exc)})
            try:
                raw = conference.result()
                if not isinstance(raw, list) or not raw:
                    raise ValueError('No conference data returned')
                events = event_rows(raw, today)
                sources.append({'name': 'developers.events', 'ok': True, 'detail': f'{len(events)} upcoming European / online events'})
            except Exception as exc:
                sources.append({'name': 'developers.events', 'ok': False, 'detail': 'Keeping cached events. ' + gl.short_error(exc)})
        unique = {row['url']: row for row in posts}
        gl.save_json(state_dir / 'tech.json', {'events': events, 'posts': sorted(unique.values(), key=lambda r: r.get('published') or '', reverse=True),
                                             'sources': sources, 'refreshed_at': dt.datetime.now(dt.timezone.utc).isoformat()})
        failures = [s['name'] for s in sources if not s['ok']]
        if failures:
            STATUS['error'] = 'Some sources could not refresh: ' + ', '.join(failures) + '. Cached listings remain available.'
    except Exception as exc:
        STATUS['error'] = gl.short_error(exc)
    finally:
        STATUS['running'] = False
        REFRESH_LOCK.release()
