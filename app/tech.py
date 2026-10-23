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
from zoneinfo import ZoneInfo

import discovery
import gl_common as gl
import tech_sources as providers

CATALOG = json.loads((Path(__file__).parent / 'content/tech.json').read_text())
EUROPE = set('Albania Andorra Austria Belarus Belgium Bosnia Bulgaria Croatia Cyprus Czechia Denmark Estonia Finland France Germany Greece Hungary Iceland Ireland Italy Kosovo Latvia Liechtenstein Lithuania Luxembourg Malta Moldova Monaco Montenegro Netherlands Norway Poland Portugal Romania Russia Serbia Slovakia Slovenia Spain Sweden Switzerland Turkey Ukraine'.split()) | {'United Kingdom', 'Czech Republic', 'North Macedonia', 'Bosnia and Herzegovina', 'The Netherlands', 'Online'}
FEEDS = [
    ('GitHub Blog', 'https://github.blog/feed/'),
    ('Cloudflare Blog', 'https://blog.cloudflare.com/rss/'),
    ('Google Developers Blog', 'https://developers.googleblog.com/feeds/posts/default?alt=rss'),
    ('Mozilla Hacks', 'https://hacks.mozilla.org/feed/'),
    ('Rust Blog', 'https://blog.rust-lang.org/feed.xml'),
    ('Go Blog', 'https://go.dev/blog/feed.atom'),
    ('Kubernetes Blog', 'https://kubernetes.io/feed.xml'),
    ('JetBrains Blog', 'https://blog.jetbrains.com/feed/'),
    ('Stack Overflow Blog', 'https://stackoverflow.blog/feed/'),
    ('Engineering at Meta', 'https://engineering.fb.com/feed/'),
]
CONFERENCES = 'https://developers.events/all-events.json'
REFRESH_LOCK = threading.Lock()
STATUS = {'running': False, 'error': ''}
BASEMAP = json.loads((Path(__file__).parent / 'content/political-map.json').read_text())
# The public Google calendar behind python.org/events (Python Software Foundation).
PYTHON_CALENDARS = {
    'Python events calendar': ('j7gov1cmnqr9tvg14k621j7t5c@group.calendar.google.com', 'https://www.python.org/events/python-events/'),
}
# Worldwide listings: without a stated country an event is left out rather than guessed.
WORLDWIDE = {'Devpost', 'Major League Hacking', *PYTHON_CALENDARS}
EVENT_SOURCES = ('developers.events', 'CCC calendar', 'Maschinendeck Trier', 'Silicon Luxembourg calendar', 'Major League Hacking', 'Devpost', *PYTHON_CALENDARS)
MASCHINENDECK_CALENDAR = 'https://nextcloud.maschinendeck.org/remote.php/dav/public-calendars/tCy8jLHHdX3oRWQG'


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


@functools.lru_cache(maxsize=2000)
def stated_country(venue):
    aliases = {'Deutschland':'Germany', 'Schweiz':'Switzerland', 'Belgique':'Belgium', 'Nederland':'Netherlands',
               'England':'United Kingdom','Scotland':'United Kingdom','Wales':'United Kingdom',
               'USA':'United States', 'United States':'United States', 'Canada':'Canada'}
    matches = {target for word,target in aliases.items() if re.search(r'\b'+re.escape(word)+r'\b', venue,re.I)}
    matches.update(c for c in EUROPE if c != 'Online' and re.search(r'\b'+re.escape(c)+r'\b',venue,re.I))
    return matches.pop() if len(matches) == 1 else ''


@functools.lru_cache(maxsize=2000)
def venue_location(venue, country=''):
    """Match named cities in a venue, checking country and excluding ambiguity."""
    country = stated_country(venue) or country
    names = {**{city:(place['lat'],place['lon'],place['country']) for city,place in discovery.PLACES.items()},
             **{row['name']:(row['lat'],row['lon'],'') for row in BASEMAP['cities']}}
    hits = []
    for name,(lat,lon,known_country) in names.items():
        if not re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)',venue,re.I):
            continue
        candidate_country = known_country
        if not candidate_country:
            candidate_country = next((c['properties']['name'] for c in BASEMAP['countries']['features'] if contains(c['geometry'],lat,lon)), '')
        if country and candidate_country != country:
            continue
        hits.append((name, candidate_country))
    if not hits:
        return '',country
    longest = max(len(name) for name,_ in hits)
    hits = [pair for pair in hits if len(pair[0]) == longest]
    return hits[0] if len(set(hits)) == 1 else ('',country)


def locate_events(rows):
    result = []
    for row in rows:
        item = dict(row)
        if item.get('online'):
            item.update(city='Online',country='',location=None)
        else:
            city, country = item.get('city',''), item.get('country','')
            if item.get('source') == 'Devpost' and not country and not stated_country(item.get('venue','')):
                # A worldwide directory's "London" could also mean Canada.
                # Require a stated country instead of guessing from our map.
                continue
            if not city or not city_location(city,country):
                named_city, named_country = venue_location(', '.join(filter(None,[city,item.get('venue','')])),country)
                if named_city:
                    city,country = named_city,named_country
                elif not country:
                    country = named_country  # A stated country still counts without a mapped city.
            if country and country not in EUROPE:
                continue
            if not country and item.get('source') in WORLDWIDE:
                continue
            item.update(city=city or 'Location not provided',country=country or 'Country not provided',location=city_location(city,country))
        if item['kind'] == 'event':
            if re.search(r'hackathon',item['title'],re.I):
                item['kind'] = 'hackathon'
            elif re.search(r'conference|congress|fosdem|konferenz',item['title'],re.I):
                item['kind'] = 'conference'
        result.append(item)
    return result


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
                       'authority':'directory', 'topics':[str(t)[:60] for t in row.get('tags',[]) if isinstance(t,str)],
                       'description': 'Community-listed event. Check the organiser’s page for programme, tickets and changes.'})
    return result


def upcoming(rows, today):
    unique, by_url = {}, {}
    def identity(row):
        parsed = urllib.parse.urlsplit(row.get('url',''))
        return (str(parsed.hostname).removeprefix('www.'),parsed.path.rstrip('/'),row.get('start'))
    cancelled = {identity(r) for r in rows if r.get('cancelled')}
    for row in rows:
        try:
            start = dt.date.fromisoformat(row['start'])
            end = dt.date.fromisoformat(row.get('end') or row['start'])
            checked = dt.date.fromisoformat(row['checked_at'])
        except (KeyError, ValueError, TypeError):
            continue
        if end < today or end < start or row.get('cancelled') or identity(row) in cancelled or not valid_url(row.get('url', '')):
            continue
        key = (re.sub(r'\W', '', re.sub(r'\b20\d\d\b', '', row['title'].casefold())), row['start'])
        parsed = urllib.parse.urlsplit(row['url'])
        url_key = (parsed.hostname.removeprefix('www.'),parsed.path.rstrip('/'),row['start'])
        existing_key = by_url.setdefault(url_key, key)
        old = unique.get(existing_key)
        item = {**row, 'location': None if row.get('online') else row.get('location') or city_location(row.get('city'), row.get('country', 'Germany')),
                'stale': (today - checked).days > 14, 'ongoing': start <= today <= end, '_url_key':url_key}
        provenance = list(old.get('listed_by',[])) if old else []
        entry = {'name':row.get('source','Source'), 'url':row.get('source_url') or row['url']}
        if entry not in provenance:
            provenance.append(entry)
        if old:
            ranks = {'directory':0,'curated':1,'calendar':2}
            preferred, other = (item,old) if ranks.get(item.get('authority','curated'),1) >= ranks.get(old.get('authority','curated'),1) else (old,item)
            item = {**other, **{k:v for k,v in preferred.items() if v not in ('',None,[])}}
        item['listed_by'] = provenance
        unique[existing_key] = item
    for row in unique.values():
        row.pop('_url_key',None)
    return sorted(unique.values(), key=lambda r: (r['start'], r['title']))


_PUBLIC = {'key': None, 'value': None}


def public_state(state_dir, today):
    # Rebuilt only when tech.json changes or the day turns; the UI asks on every poll.
    path = state_dir / 'tech.json'
    try:
        key = (path.stat().st_mtime_ns, today)
    except OSError:
        key = (None, today)
    if _PUBLIC['key'] != key:
        cached = gl.load_json(path, {})
        events = upcoming([*cached.get('events', []), *CATALOG['events']], today)
        bases = {city: {'city':city, **place} for city, place in discovery.PLACES.items()}
        bases.update({row['city']:{'city':row['city'], **row['location']} for row in events if row.get('location')})
        _PUBLIC.update(key=key, value={'events': events,
            'posts': cached.get('posts', []), 'sources': cached.get('sources', []),
            'calendars': CATALOG['calendars'], 'checked_at': CATALOG['checked_at'],
            'bases': sorted(bases.values(), key=lambda p:p['city']),
            'refreshed_at': cached.get('refreshed_at')})
    return {**_PUBLIC['value'], **STATUS}


def maschinendeck_events(today):
    """The public calendar export first, then the space's own event API."""
    end = today + dt.timedelta(days=90)
    berlin = ZoneInfo('Europe/Berlin')
    span = [int(dt.datetime.combine(day, dt.time(), berlin).timestamp()) for day in (today, end)]
    rows, errors = None, []
    try:
        # Nextcloud expands the weekly meetings server-side for the requested window.
        rows = providers.maschinendeck_calendar_rows(gl.http_get(f'{MASCHINENDECK_CALENDAR}?export&expand=1&start={span[0]}&end={span[1]}'), today)
        if rows:
            return rows
    except Exception as exc:
        errors.append('calendar export: ' + gl.short_error(exc))
    try:
        return providers.maschinendeck_rows(gl.http_json(f'https://nextcloud.maschinendeck.org/rest/?from={today:%Y%m%d}&to={end:%Y%m%d}'), today)
    except Exception as exc:
        if rows is not None:
            return rows
        errors.append('event API: ' + gl.short_error(exc))
    raise ValueError('; '.join(errors))


def fetch_event_source(name, today):
    if name == 'developers.events':
        raw = gl.http_json(CONFERENCES)
        if not isinstance(raw,list) or not raw:
            raise ValueError('No conference data returned')
        return event_rows(raw,today)
    if name == 'CCC calendar':
        return locate_events(providers.ical_rows(gl.http_get('https://events.ccc.de/calendar/events.ics'), name, 'https://events.ccc.de/calendar/', today))
    if name == 'Maschinendeck Trier':
        return locate_events(maschinendeck_events(today))
    if name in PYTHON_CALENDARS:
        calendar, page = PYTHON_CALENDARS[name]
        # Google serves public calendars at both addresses; python.org's wiki lists the second.
        for host in ('https://calendar.google.com/calendar', 'https://www.google.com/calendar'):
            try:
                payload = gl.http_get(f'{host}/ical/{urllib.parse.quote(calendar)}/public/basic.ics')
                break
            except Exception:
                if host.startswith('https://www.'):
                    raise
        return locate_events(providers.ical_rows(payload, name, page, today, link_in_description=True))
    if name == 'Silicon Luxembourg calendar':
        url = 'https://www.siliconluxembourg.lu/calendar/'
        rows = providers.ical_rows(gl.http_get(url+'?ical=1'),name,url,today)
        try:
            page = gl.http_get(url)
            rich = providers.structured_rows(page,name,url,today)
            prices = providers.visible_prices(page)
            index = {(r['url'],r['start']):r for r in rich}
            for row in rows:
                extra = index.get((row['url'],row['start']),{})
                for key in ('venue','city','country','organizer','registration_url','cancelled'):
                    if extra.get(key):
                        row[key] = extra[key]
                row['cost'] = prices.get(row['url'],'')
        except Exception:
            # The calendar remains usable when optional page metadata is blocked.
            pass
        return locate_events(rows)
    if name == 'Major League Hacking':
        season = today.year + (today.month >= 7)
        url = f'https://www.mlh.com/seasons/{season}/events'
        return locate_events(providers.mlh_rows(gl.http_get(url),url,today))
    if name == 'Devpost':
        rows = []
        # Devpost's public search API caps pages at 40. Bound refresh work to
        # five pages; never imply this is the whole worldwide directory.
        for page in range(1,6):
            url = f'https://devpost.com/api/hackathons?status%5B%5D=open&status%5B%5D=upcoming&per_page=40&page={page}'
            payload = gl.http_json(url)
            rows.extend(providers.devpost_rows(payload,today))
            meta = payload.get('meta') or {}
            if not payload['hackathons'] or page * int(meta.get('per_page') or 40) >= int(meta.get('total_count') or 0):
                break
        return locate_events(rows)
    raise ValueError('Unknown technology source')


def refresh(state_dir, today):
    if not REFRESH_LOCK.acquire(blocking=False):
        return
    STATUS.update(running=True, error='')
    try:
        cached = gl.load_json(state_dir / 'tech.json', {})
        sources, posts = [], []
        event_sources = cached.get('event_sources', {'developers.events':cached.get('events',[])})
        previous_status = {row['name']:row for row in cached.get('sources',[]) if 'name' in row}
        checked = dt.datetime.now(dt.timezone.utc).isoformat()
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
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            tasks = {pool.submit(fetch_posts, name, url): name for name, url in FEEDS}
            event_tasks = {pool.submit(fetch_event_source,name,today):name for name in EVENT_SOURCES}
            for future, name in tasks.items():
                try:
                    rows = future.result()
                    posts.extend(rows)
                    sources.append({'name': name, 'type':'posts', 'ok': True, 'detail': f'{len(rows)} recent posts', 'last_success_at':checked})
                except Exception as exc:
                    posts.extend(row for row in cached.get('posts', []) if row.get('source') == name)
                    sources.append({'name': name, 'type':'posts', 'ok': False, 'detail': 'Keeping cached posts. ' + gl.short_error(exc),
                                    'last_success_at':previous_status.get(name,{}).get('last_success_at')})
            for future,name in event_tasks.items():
                try:
                    rows = future.result()
                    event_sources[name] = rows
                    sources.append({'name':name,'type':'events','ok':True,'detail':f'{len(rows)} upcoming / ongoing listings', 'last_success_at':checked})
                except Exception as exc:
                    sources.append({'name':name,'type':'events','ok':False,'detail':'Keeping cached events. '+gl.short_error(exc),
                                    'last_success_at':previous_status.get(name,{}).get('last_success_at')})
        events = [row for rows in event_sources.values() for row in rows]
        unique = {row['url']: row for row in posts}
        gl.save_json(state_dir / 'tech.json', {'events': events, 'event_sources':event_sources,
                                             'posts': sorted(unique.values(), key=lambda r: r.get('published') or '', reverse=True),
                                             'sources': sources, 'refreshed_at':checked})
        failures = [s['name'] for s in sources if not s['ok']]
        if failures:
            STATUS['error'] = 'Some sources could not refresh: ' + ', '.join(failures) + '. Cached listings remain available.'
    except Exception as exc:
        STATUS['error'] = gl.short_error(exc)
    finally:
        STATUS['running'] = False
        REFRESH_LOCK.release()
