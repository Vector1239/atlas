import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP.parent / 'germany-life-hermes/scripts'))
import tech


class TechTests(unittest.TestCase):
    def test_feed_keeps_upcoming_europe_and_online_not_past_cancelled_or_bad_urls(self):
        def row(**extra):
            return {'name':'Developer conference', 'country':'Germany', 'city':'Berlin', 'date':[1792886400000,1792972800000], 'hyperlink':'https://organiser.example/2026', **extra}
        data = [row(), row(country='USA'), row(country='USA',location='Online',name='Online event'), row(status='cancelled'), row(hyperlink='javascript:alert(1)'), row(date=[0,1]), row(date=['bad'])]
        rows = tech.event_rows(data, dt.date(2026,10,17))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['location']['label'], 'Berlin')
        self.assertTrue(rows[1]['online'])
        self.assertIsNone(rows[1]['location'])

    def test_unknown_location_does_not_get_a_fake_pin(self):
        rows = tech.event_rows([{'name':'Conference', 'city':'Unknown city','country':'Germany','date':[1792886400000], 'hyperlink':'https://organiser.example/'}], dt.date(2026,10,17))
        self.assertIsNone(rows[0]['location'])

    def test_bundled_city_centres_match_the_requested_country(self):
        self.assertAlmostEqual(tech.city_location('Brussels', 'Belgium')['lat'], 50.8353)
        self.assertIsNone(tech.city_location('Brussels', 'Germany'))
        self.assertAlmostEqual(tech.city_location('Munich', 'Germany')['lon'], 11.573)

    def test_expired_catalog_entries_disappear_and_old_checks_are_flagged(self):
        row = {'title':'Hackathon', 'start':'2026-10-20','end':'2026-10-23','checked_at':'2026-09-01','url':'https://organiser.example/'}
        self.assertTrue(tech.upcoming([row], dt.date(2026,10,21))[0]['stale'])
        self.assertEqual(tech.upcoming([row], dt.date(2026,10,24)), [])

    def test_failed_refresh_preserves_cached_events_and_posts(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            cached = {'events':[{'id':'cached'}], 'posts':[{'source':tech.FEEDS[0][0], 'title':'Cached post', 'url':'https://blog.example/post'}]}
            (state / 'tech.json').write_text(json.dumps(cached))
            with patch.object(tech.gl, 'http_get', side_effect=OSError('offline')), patch.object(tech.gl, 'http_json', side_effect=OSError('offline')):
                tech.refresh(state, dt.date(2026,10,17))
            saved = json.loads((state / 'tech.json').read_text())
            self.assertEqual(saved['events'], cached['events'])
            self.assertEqual(saved['posts'], cached['posts'])
            self.assertTrue(all(not row['ok'] for row in saved['sources']))

    def test_duplicates_combine_sources_and_prefer_live_calendar_details(self):
        row = {'title':'Build 2026','start':'2026-10-22','end':'2026-10-22','checked_at':'2026-10-17','url':'https://event.example/','source':'Directory','authority':'directory'}
        official = {**row,'title':'Build Conference','url':'https://www.event.example/','source':'Organiser calendar','authority':'calendar','venue':'Actual room','cost':'Free'}
        result = tech.upcoming([row,official],dt.date(2026,10,17))
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['cost'],'Free')
        self.assertEqual({r['name'] for r in result[0]['listed_by']},{'Directory','Organiser calendar'})
        self.assertEqual(tech.upcoming([row,{**official,'cancelled':True}],dt.date(2026,10,17)),[])

    def test_source_failure_preserves_only_that_sources_cache(self):
        cached = {'event_sources':{'developers.events':[{'id':'old-directory'}],'Major League Hacking':[{'id':'keep-mlh'}]},'events':[],'posts':[]}
        def fetch(name,today):
            if name == 'Major League Hacking':
                raise OSError('temporarily offline')
            return [{'id':'new-meetup'}] if name == 'Maschinendeck Trier' else []
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            (state/'tech.json').write_text(json.dumps(cached))
            with patch.object(tech,'fetch_event_source',side_effect=fetch), patch.object(tech.gl,'http_get',side_effect=OSError('offline')):
                tech.refresh(state,dt.date(2026,10,17))
            saved = json.loads((state/'tech.json').read_text())
            self.assertEqual(saved['event_sources']['Major League Hacking'],[{'id':'keep-mlh'}])
            self.assertEqual(saved['event_sources']['developers.events'],[])
            self.assertEqual(saved['event_sources']['Maschinendeck Trier'],[{'id':'new-meetup'}])

    def test_neighbourhood_addresses_resolve_to_a_known_city_and_global_unknowns_stay_out(self):
        rows = tech.locate_events([{'title':'Meetup','kind':'event','city':'Gare Luxembourg','country':'Luxembourg','venue':'Silversquare, Luxembourg','source':'Silicon Luxembourg calendar'}, {'title':'Hack','kind':'hackathon','city':'','country':'','venue':'Unknown international venue','source':'Devpost'}])
        self.assertEqual(len(rows),1)
        self.assertIsNotNone(rows[0]['location'])
        self.assertEqual(rows[0]['country'],'Luxembourg')
        for venue in ('London','New York, NY','University of Toronto Scarborough'):
            self.assertEqual(tech.locate_events([{'title':'Hack','kind':'hackathon','city':'','country':'','venue':venue,'source':'Devpost'}]),[])
