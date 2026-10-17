"""Keep recent stories when a publisher rotates its RSS feed."""
import datetime as dt
import re
import urllib.parse


def headline_key(item):
    title = item.get('title', '').strip()
    suffix = ' - ' + item.get('source', '')
    if suffix != ' - ' and title.casefold().endswith(suffix.casefold()):
        title = title[:-len(suffix)]
    return re.sub(r'[^\w]+', ' ', title.casefold()).strip()


def merge_news(previous, incoming, now, days=14):
    cutoff = now - dt.timedelta(days=days)
    rows, titles, urls = [], {}, {}
    # Prefer freshly fetched metadata, retaining stories no longer in the feed.
    for original in [*incoming, *previous]:
        item = dict(original)
        try:
            published = dt.datetime.fromisoformat(item.get('published') or item.get('first_seen') or now.isoformat())
            if published.tzinfo is None:
                published = published.replace(tzinfo=now.tzinfo)
            if published < cutoff or published > now + dt.timedelta(days=1):
                continue
        except (ValueError, TypeError):
            continue
        item.setdefault('first_seen', now.isoformat())
        url = item.get('article_url') or item.get('url', '')
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
            continue
        canonical = (parsed.hostname.removeprefix('www.'), parsed.path.rstrip('/'))
        title = headline_key(item)
        match = urls.get(canonical) or titles.get(title)
        if match is not None:
            # A rotating aggregator entry must not discard a known direct link.
            if parsed.hostname not in ('news.google.com', 'www.news.google.com') and not match.get('article_url'):
                match['article_url'] = url
            for key in ('image', 'image_alt', 'article_url'):
                if item.get(key) and not match.get(key):
                    match[key] = item[key]
            match['first_seen'] = min(match['first_seen'], item['first_seen'])
            urls[canonical] = match
            titles[title] = match
            continue
        rows.append(item)
        titles[title] = item
        urls[canonical] = item
    rows.sort(key=lambda row: (row.get('ring', 3),
                              not bool(re.search(r'universit|hochschul', row.get('feed', row.get('source', '')), re.I)),
                              not bool(re.search(r'trier|universit|hochschul|campus', row.get('title', ''), re.I)),
                              -(dt.datetime.fromisoformat(row.get('published') or row['first_seen']).timestamp())))
    return rows
