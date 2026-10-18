"""Read published event calendars and structured event data without a browser or AI."""
import datetime as dt
import hashlib
import html
from html.parser import HTMLParser
import json
import re
import urllib.parse
from zoneinfo import ZoneInfo

COUNTRIES = dict(zip(
    'AT BE BG CH CY CZ DE DK EE ES FI FR GB GR HR HU IE IS IT LT LU LV MT NL NO PL PT RO RS SE SI SK UA US CA IN'.split(),
    ['Austria','Belgium','Bulgaria','Switzerland','Cyprus','Czechia','Germany','Denmark','Estonia','Spain','Finland','France','United Kingdom','Greece','Croatia','Hungary','Ireland','Iceland','Italy','Lithuania','Luxembourg','Latvia','Malta','Netherlands','Norway','Poland','Portugal','Romania','Serbia','Sweden','Slovenia','Slovakia','Ukraine','United States','Canada','India']))


def plain(value, limit=600):
    value = html.unescape(html.unescape(str(value or '')))
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', value)).strip()[:limit]


def valid_url(value):
    try:
        p = urllib.parse.urlsplit(value)
        return p.scheme in ('http', 'https') and bool(p.hostname) and not p.username
    except (ValueError, TypeError, AttributeError):
        return False


def record(title, start, end, url, source, today, **extra):
    if not title or not valid_url(url):
        return None
    try:
        start_date, end_date = dt.date.fromisoformat(start[:10]), dt.date.fromisoformat(end[:10])
    except (ValueError, TypeError):
        return None
    if end_date < today or end_date < start_date:
        return None
    return {'id': hashlib.sha256(f'{source}:{url}:{start}'.encode()).hexdigest()[:16],
            'title': plain(title, 300), 'start': start_date.isoformat(), 'end': end_date.isoformat(),
            'url': url, 'source': source, 'checked_at': today.isoformat(), 'kind':'event',
            'city':'', 'country':'', 'venue':'', 'description':'', 'online':False, **extra}


def unescape_ical(value):
    return re.sub(r'\\([nN,;\\])', lambda m:'\n' if m[1].lower() == 'n' else m[1], value)


def ical_time(value, parameters):
    if re.fullmatch(r'\d{8}', value):
        return dt.datetime.strptime(value, '%Y%m%d'), True
    moment = dt.datetime.strptime(value.rstrip('Z'), '%Y%m%dT%H%M%S')
    timezone = 'UTC' if value.endswith('Z') else parameters.get('TZID')
    if timezone:
        moment = moment.replace(tzinfo=ZoneInfo(timezone.strip('"')))
    return moment, False


def ical_rows(payload, source, source_url, today):
    text = payload.decode('utf-8-sig') if isinstance(payload, bytes) else payload
    if 'BEGIN:VCALENDAR' not in text or 'END:VCALENDAR' not in text:
        raise ValueError('The source did not return a calendar')
    text = re.sub(r'\r?\n[ \t]', '', text)
    result = []
    for block in re.findall(r'BEGIN:VEVENT\r?\n(.*?)END:VEVENT', text, re.S):
        fields = {}
        for line in block.splitlines():
            key, colon, value = line.partition(':')
            parts = key.split(';')
            if colon:
                fields[parts[0].upper()] = (value, dict(p.split('=',1) for p in parts[1:] if '=' in p))
        # Recurring series need expanded occurrences, not an invented next date.
        # Maschinendeck's published API supplies those expanded instances.
        if 'RRULE' in fields or 'DTSTART' not in fields:
            continue
        try:
            start, all_day = ical_time(*fields['DTSTART'])
            end, end_all_day = ical_time(*fields.get('DTEND', fields['DTSTART']))
            if all_day and end_all_day and end > start:
                end -= dt.timedelta(days=1)  # RFC 5545 all-day DTEND is exclusive.
            value = lambda key: unescape_ical(fields.get(key, ('', {}))[0])
            venue = plain(value('LOCATION'), 400)
            if not venue:
                labelled = re.search(r'(?:^|\n)(?:Place|Venue|Location|Ort):\s*([^\n]+)',value('DESCRIPTION'),re.I)
                if labelled:
                    venue = plain(re.split(r'Please note',labelled[1],maxsplit=1,flags=re.I)[0],400)
            time_note = '' if all_day else f'{start:%H:%M}–{end:%H:%M} {start.tzname() or "source local time"}'
            item = record(value('SUMMARY'), start.isoformat(), end.isoformat(), value('URL') or source_url, source, today,
                          venue=venue, description=plain(value('DESCRIPTION')),
                          time_note=time_note, starts_at=start.isoformat() if not all_day else '',
                          ends_at=end.isoformat() if not all_day else '',
                          cancelled=value('STATUS').upper() == 'CANCELLED',
                          online=bool(re.fullmatch(r'(?:online|virtual|remote|zoom|webinar)(?:\s+event)?', venue, re.I)),
                          topics=[plain(t,60) for t in value('CATEGORIES').split(',') if t],
                          authority='calendar', source_url=source_url)
            if item:
                result.append(item)
        except (ValueError, KeyError, TypeError):
            continue
    return result


def maschinendeck_rows(payload, today):
    if not isinstance(payload, dict) or payload.get('code') != 200 or not isinstance(payload.get('data'), list):
        raise ValueError('Maschinendeck did not return its public event list')
    rows = []
    for event in payload['data']:
        try:
            start = dt.datetime.fromisoformat(event['dtstart']).astimezone(ZoneInfo('Europe/Berlin'))
            end = dt.datetime.fromisoformat(event.get('dtend') or event['dtstart']).astimezone(ZoneInfo('Europe/Berlin'))
            item = record(event.get('summary'), start.isoformat(), end.isoformat(), 'https://maschinendeck.org/', 'Maschinendeck Trier', today,
                          city='Trier', country='Germany', venue=plain(event.get('location'),400),
                          description=plain(event.get('description')) or 'Open hacker and maker community meeting. See the public calendar for participation details.',
                          time_note=f'{start:%H:%M}–{end:%H:%M} {start.tzname()}', starts_at=start.isoformat(), ends_at=end.isoformat(),
                          series_id=plain(event.get('uid'),300),
                          cancelled=str(event.get('status','')).upper() == 'CANCELLED',
                          source_url='https://maschinendeck.org/', authority='calendar',
                          calendar_url='https://nextcloud.maschinendeck.org/index.php/apps/calendar/p/tCy8jLHHdX3oRWQG')
            if item:
                rows.append(item)
        except (KeyError, ValueError, TypeError):
            continue
    return rows


class MLHParser(HTMLParser):
    """Read the schema.org Event microdata published in MLH's schedule."""
    VOID = {'meta','img','br','hr','input','link','source','wbr','area','base','embed','param','track','col'}
    def __init__(self):
        super().__init__()
        self.stack, self.events, self.event = [], [], None
    def handle_starttag(self, tag, attributes):
        attrs = {k.lower():v for k,v in attributes}
        if str(attrs.get('itemtype','')).rstrip('/').endswith('/Event'):
            self.event = {'root_depth':len(self.stack), 'url':attrs.get('href',''), 'title':''}
        if self.event is not None and tag == 'meta' and attrs.get('itemprop'):
            self.event[attrs['itemprop'].lower()] = attrs.get('content','')
        if tag not in self.VOID:
            self.stack.append((tag, attrs))
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)
    def handle_data(self, text):
        if self.event is not None and any(tag == 'h4' for tag, _ in self.stack):
            self.event['title'] += text
    def handle_endtag(self, tag):
        match = next((i for i in range(len(self.stack)-1,-1,-1) if self.stack[i][0] == tag), None)
        if match is None:
            return
        del self.stack[match:]
        if self.event is not None and len(self.stack) <= self.event['root_depth']:
            self.events.append(self.event)
            self.event = None


def mlh_rows(payload, source_url, today):
    parser = MLHParser()
    parser.feed(payload.decode('utf-8') if isinstance(payload,bytes) else payload)
    if not parser.events:
        raise ValueError('MLH’s published event markup could not be read')
    result = []
    for event in parser.events:
        item = record(event['title'], event.get('startdate',''), event.get('enddate',''), event.get('url',''), 'Major League Hacking', today,
                      kind='hackathon', city=event.get('addresslocality',''), country=COUNTRIES.get(event.get('addresscountry',''), event.get('addresscountry','')),
                      online='OnlineEventAttendanceMode' in event.get('eventattendancemode',''),
                      cost='Free entry (MLH listing)' if event.get('isaccessibleforfree') == 'true' else '',
                      description='MLH member hackathon. Check the organiser’s rules, eligibility and registration availability.',
                      source_url=source_url, authority='directory')
        if item:
            result.append(item)
    return result


def submission_dates(value):
    """Devpost's displayed submission window; never label it as the venue dates."""
    month = r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
    match = re.fullmatch(month + r'\s+(\d{1,2})(?:,\s*(20\d\d))?\s*[-–]\s*(?:' + month + r'\s+)?(\d{1,2}),\s*(20\d\d)', value.strip())
    if not match:
        raise ValueError('Submission dates could not be read unambiguously')
    sm, sd, sy, em, ed, ey = match.groups()
    em = em or sm
    start_month, end_month = dt.datetime.strptime(sm,'%b').month, dt.datetime.strptime(em,'%b').month
    end_year = int(ey)
    start_year = int(sy) if sy else end_year - (start_month > end_month)
    return dt.date(start_year,start_month,int(sd)).isoformat(), dt.date(end_year,end_month,int(ed)).isoformat()


def devpost_rows(payload, today):
    if not isinstance(payload,dict) or not isinstance(payload.get('hackathons'),list):
        raise ValueError('Devpost did not return a hackathon list')
    result = []
    for event in payload['hackathons']:
        if event.get('open_state') not in ('open','upcoming'):
            continue
        try:
            start, end = submission_dates(event.get('submission_period_dates',''))
            venue = plain((event.get('displayed_location') or {}).get('location'),250)
            prize = plain(event.get('prize_amount'),100)
            digits = re.sub(r'\D','',prize)
            if digits and not int(digits):
                prize = ''
            item = record(event.get('title'), start, end, event.get('url',''), 'Devpost', today,
                          kind='hackathon', venue=venue, online=venue.casefold() == 'online',
                          description='The dates show the submission window. Check the organiser’s rules for eligibility and participation.',
                          date_note='Submission window', deadline=end, prize=prize,
                          organizer=plain(event.get('organization_name'),150),
                          eligibility='Invitation required' if event.get('invite_only') else '',
                          topics=[plain(t.get('name'),60) for t in event.get('themes',[]) if isinstance(t,dict) and t.get('name')],
                          source_url='https://devpost.com/hackathons', authority='directory')
            if item:
                result.append(item)
        except (ValueError, TypeError):
            continue
    return result


class LinkedData(HTMLParser):
    def __init__(self):
        super().__init__()
        self.capture, self.buffer, self.documents = False, [], []
    def handle_starttag(self,tag,attrs):
        if tag == 'script' and dict(attrs).get('type') == 'application/ld+json':
            self.capture, self.buffer = True, []
    def handle_data(self,data):
        if self.capture:
            self.buffer.append(data)
    def handle_endtag(self,tag):
        if tag == 'script' and self.capture:
            try:
                self.documents.append(json.loads(''.join(self.buffer)))
            except ValueError:
                pass
            self.capture = False


class VisiblePrices(HTMLParser):
    """Prefer the visible ticket label over inconsistent calendar JSON currency."""
    def __init__(self):
        super().__init__()
        self.article, self.price, self.text, self.links, self.prices = False, False, [], set(), {}
    def handle_starttag(self,tag,attrs):
        attrs = dict(attrs)
        if tag == 'article' and 'tribe-events-calendar-list__event' in attrs.get('class',''):
            self.article, self.text, self.links = True, [], set()
        if self.article and tag == 'a' and valid_url(attrs.get('href')):
            self.links.add(attrs['href'])
        if self.article and tag == 'span' and 'tribe-events-c-small-cta__price' in attrs.get('class',''):
            self.price = True
    def handle_data(self,value):
        if self.price:
            self.text.append(value)
    def handle_endtag(self,tag):
        if tag == 'span':
            self.price = False
        if tag == 'article' and self.article:
            label = plain(''.join(self.text),100)
            if label:
                self.prices.update({link:label for link in self.links})
            self.article = self.price = False


def visible_prices(payload):
    parser = VisiblePrices()
    parser.feed(payload.decode('utf-8') if isinstance(payload,bytes) else payload)
    return parser.prices


def structured_rows(payload, source, source_url, today):
    parser = LinkedData()
    parser.feed(payload.decode('utf-8') if isinstance(payload,bytes) else payload)
    def walk(value):
        if isinstance(value,list):
            for child in value:
                yield from walk(child)
        elif isinstance(value,dict):
            types = value.get('@type',[])
            if any(str(t).rsplit('/',1)[-1].endswith('Event') for t in (types if isinstance(types,list) else [types])):
                yield value
            for key in ('@graph','itemListElement','item'):
                if key in value:
                    yield from walk(value[key])
    result = []
    for event in walk(parser.documents):
        location = event.get('location') or {}
        if not isinstance(location,dict):
            location = {}
        address = location.get('address') or {}
        if not isinstance(address,dict):
            address = {'streetAddress':plain(address)}
        country = address.get('addressCountry') or ''
        if isinstance(country,dict):
            country = country.get('name','')
        offers = event.get('offers') or {}
        offers = offers[0] if isinstance(offers,list) and offers else offers
        offers = offers if isinstance(offers,dict) else {}
        organizer = event.get('organizer') or {}
        organizer = organizer if isinstance(organizer,dict) else {}
        cost = 'Free entry' if event.get('isAccessibleForFree') is True else ''
        if str(offers.get('price','')):
            cost = f"{offers.get('price')} {offers.get('priceCurrency') or ''}".strip()
        start = str(event.get('startDate') or '')
        end = str(event.get('endDate') or start)
        item = record(event.get('name'),start,end,event.get('url') or source_url,source,today,
                      city=plain(address.get('addressLocality'),120), country=COUNTRIES.get(country,country),
                      venue=plain(', '.join(str(v) for v in [location.get('name'),address.get('streetAddress'),address.get('addressLocality')] if v),400),
                      description=plain(event.get('description')), cost=plain(cost,100), organizer=plain(organizer.get('name'),150),
                      online='OnlineEventAttendanceMode' in str(event.get('eventAttendanceMode','')),
                      cancelled=str(event.get('eventStatus','')).endswith('EventCancelled'),
                      registration_url=offers.get('url') if valid_url(offers.get('url')) else '',
                      starts_at=start if 'T' in start else '', ends_at=end if 'T' in end else '',
                      authority='calendar', source_url=source_url)
        if item:
            result.append(item)
    return result
