import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import subprocess
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

APP = Path(__file__).resolve().parents[1]
SOURCE = APP.parent / 'germany-life-hermes'


class AtlasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.project = Path(cls.tmp.name)
        for directory in ('scripts', 'config', 'templates'):
            shutil.copytree(SOURCE / directory, cls.project / directory)
        (cls.project / 'data').mkdir()
        for name in ('deadlines.toml', 'worklog.csv', 'job_feedback.csv'):
            shutil.copy(cls.project / 'templates' / name, cls.project / 'data' / name)
        shutil.copy(cls.project / 'templates/profile.md', cls.project / 'profile.md')
        cls.old_env = os.environ.get('ATLAS_PROJECT')
        os.environ['ATLAS_PROJECT'] = str(cls.project)
        os.environ['HERMES_HOME'] = str(cls.project / 'hermes-home')
        spec = importlib.util.spec_from_file_location('atlas_backend_test', APP / 'backend.py')
        cls.backend = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.backend)
        cls.server = cls.backend.ThreadingHTTPServer(('127.0.0.1', 0), cls.backend.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()
        if cls.old_env is None:
            os.environ.pop('ATLAS_PROJECT', None)
        else:
            os.environ['ATLAS_PROJECT'] = cls.old_env

    def post(self, path, data, origin=None, authenticated=True):
        headers = {'Content-Type': 'application/json'}
        if authenticated:
            headers['X-Atlas-Token'] = self.backend.TOKEN
        if origin:
            headers['Origin'] = origin
        req = urllib.request.Request(self.url + path, data=json.dumps(data).encode(), headers=headers)
        return urllib.request.urlopen(req)

    def test_private_api_requires_launch_session(self):
        with self.assertRaises(urllib.error.HTTPError) as result:
            urllib.request.urlopen(self.url + '/api/state')
        self.assertEqual(result.exception.code, 401)

    def test_job_provider_key_is_saved_locally_and_never_returned(self):
        secret = 'private-jsearch-test-key'
        with self.post('/api/jobs/provider', {'host': 'openwebninja', 'key': secret}) as response:
            result = json.load(response)
        self.assertTrue(result['provider']['configured'])
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn(secret, json.dumps(self.backend.public_state()))
        path = self.project / 'state/job_credentials.json'
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.post('/api/jobs/provider', {'host': 'openwebninja', 'key': ''}).close()
        self.assertFalse(self.backend.public_state()['job_provider']['configured'])

    def test_standard_refresh_preserves_saved_jsearch_jobs_and_disallows_paid_requests(self):
        b=self.backend
        today=b.dt.date.today().isoformat()
        cached={'id':b.gl.short_id('JSearch:cached'),'source':'JSearch','source_id':'cached','title':'Data Scientist',
                'company':'Saved company','ring':2,'where':'Berlin','posted':today,'url':'https://jobs.example/cached','text':'','flags':[]}
        free={**cached,'source':'Bundesagentur','source_id':'free','title':'Data Analyst','company':'Free company','url':'https://jobs.example/free'}
        cfg={'jobs':{'include':['data']}}
        with patch.dict(b.CACHE,{'jobs':[cached],'news':[]}), patch.object(b,'config',return_value=cfg), \
                patch.object(b.morning_brief,'weather',return_value=[]), patch.object(b.morning_brief,'mensa_menu',return_value=[]), \
                patch.object(b.NEWS_MEDIA,'start'), patch.object(b.job_scan,'fetch_bundesagentur',return_value=[free]), \
                patch.object(b.job_scan,'fetch_arbeitnow',return_value=[]), patch.object(b.job_scan,'fetch_jsearch',return_value=[]) as paid, \
                patch.object(b.job_scan,'fetch_remote',return_value=[]):
            b.refresh_data()
            self.assertEqual(b.REFRESH_STATUS['error'],'')
            self.assertEqual({job['source'] for job in b.CACHE['jobs']},{'JSearch','Bundesagentur'})
            self.assertFalse(paid.call_args.kwargs['allow_network'])

    def test_refresh_gives_every_job_a_unique_id_when_short_ids_collide(self):
        b=self.backend
        today=b.dt.date.today().isoformat()
        first={'source':'Arbeitnow','source_id':'tester-a','title':'Softwaretester','company':'Hallo Welt! GmbH','ring':1,
               'where':'Regensburg','posted':today,'url':'https://jobs.example/a','text':'','flags':[]}
        second={**first,'source_id':'analyst-b','title':'Data Analyst','url':'https://jobs.example/b'}
        with patch.dict(b.CACHE,{'jobs':[],'news':[]}), patch.object(b,'config',return_value={'jobs':{'include':['data']}}), \
                patch.object(b.morning_brief,'weather',return_value=[]), patch.object(b.morning_brief,'mensa_menu',return_value=[]), \
                patch.object(b.NEWS_MEDIA,'start'), patch.object(b.job_scan,'fetch_bundesagentur',return_value=[]), \
                patch.object(b.job_scan,'fetch_arbeitnow',return_value=[first,second]), patch.object(b.job_scan,'fetch_jsearch',return_value=[]), \
                patch.object(b.job_scan,'fetch_remote',return_value=[]), patch.object(b.gl,'short_id',return_value='J-same'):
            b.refresh_data()
            ids=[job['id'] for job in b.CACHE['jobs']]
            self.assertEqual(len(ids),2)
            self.assertEqual(len(set(ids)),2)
            self.assertIn('J-same',ids)

    def test_only_explicit_jsearch_action_authorizes_paid_refresh(self):
        b=self.backend
        cfg={'jobs':{'jsearch':{'searches':[{'what':'data'}]}}}
        with patch.object(b.threading,'Thread') as worker, patch.object(b.job_providers,'provider_state',return_value={'configured':True}), \
                patch.object(b,'config',return_value=cfg):
            b.api_post('/api/refresh',{})
            self.assertNotIn('kwargs',worker.call_args.kwargs)
            worker.reset_mock()
            b.api_post('/api/jobs/jsearch',{})
            self.assertEqual(worker.call_args.kwargs['kwargs'],{'include_jsearch':True})
        with patch.object(b.threading,'Thread') as worker, patch.object(b.job_providers,'provider_state',return_value={'configured':False}):
            with self.assertRaisesRegex(ValueError,'Save a JSearch key'):
                b.api_post('/api/jobs/jsearch',{})
            worker.assert_not_called()

    def test_job_details_only_fetch_known_listings_and_update_requirement_flags(self):
        job = {'id': 'J-detail', 'source': 'Bundesagentur', 'source_id': '10000-test-S',
               'title': 'Working Student Data Science', 'company': 'Example', 'ring': 0,
               'where': 'Trier', 'posted': '', 'url': 'https://www.arbeitsagentur.de/jobsuche/jobdetail/10000-test-S', 'text': ''}
        with patch.dict(self.backend.CACHE, {'jobs': [job]}), patch.object(self.backend.job_details, 'load', return_value={
            'text': 'We require fluent German and Python experience.', 'detail_source': 'Bundesagentur job details'}) as fetch:
            with self.assertRaises(urllib.error.HTTPError):
                self.post('/api/jobs/details', {'id': 'unknown', 'url': 'http://127.0.0.1/private'})
            fetch.assert_not_called()
            with self.post('/api/jobs/details', {'id': 'J-detail'}) as response:
                self.assertIn('fluent German', json.load(response)['text'])
            self.assertIn('german-required', self.backend.CACHE['jobs'][0]['flags'])
            self.assertIn('fluent German', self.backend.public_state()['jobs'][0]['text'])

    def test_brief_keeps_english_source_facts_and_renders_real_list_items(self):
        rows = [{'title':'Russia targets Ukraine’s electricity supply', 'language':'en', 'source':'Publisher', 'url':'https://publisher.example/news'}]
        result = self.backend.attach_brief_links('Europe:\n• Starlink restrictions [news-0]', rows)
        self.assertIn('- [Russia targets Ukraine’s electricity supply][news-0] · Publisher', result)
        self.assertNotIn('Starlink', result)

    def test_brief_regions_follow_source_records_not_model_guesses(self):
        rows = [{'title':'Trier campus update - Publisher', 'language':'en', 'ring':0, 'source':'Publisher', 'url':'https://publisher.example/news'}]
        result = self.backend.attach_brief_links('Weather: rain\n\n**Germany**:\n- Wrong paraphrase [news-0]', rows)
        self.assertIn('**Trier**', result)
        self.assertNotIn('**Germany**', result)
        self.assertIn('[Trier campus update][news-0] · Publisher', result)
        self.assertIn('Weather: rain', result)

    def test_brief_keeps_lines_between_regions_and_does_not_repeat_news(self):
        rows = [{'title': f'Story {i}', 'language': 'en', 'ring': ring, 'source': 'P', 'url': f'https://p.example/{i}'}
                for i, ring in enumerate((0, 0, 2))]
        text = ('- Early pick [news-1]\n**Trier**:\n- A [news-0]\n⏰ **Deadlines**: pay rent\n'
                '**Germany**:\n- B [news-2]\n🍽️ Mensa: soup')
        result = self.backend.attach_brief_links(text, rows)
        self.assertIn('⏰ **Deadlines**: pay rent', result)
        self.assertIn('🍽️ Mensa: soup', result)
        self.assertEqual(result.count('][news-1]'), 1)

    def test_background_translation_leaves_chat_available_and_saves_only_one_batch(self):
        import io
        titles = [f'Neue Ausstellung Nummer {i}' for i in range(5)]
        finished = threading.Event()
        save = self.backend.gl.save_json
        def capture_save(path, value):
            save(path, value)
            if path.name == 'news_translations.json':
                finished.set()
        with patch.dict(self.backend.CACHE, {'news':[{'title':t, 'lang':'de'} for t in titles]}), patch.object(self.backend, 'model_health', return_value=True), patch.object(self.backend.hermes_link, 'complete', return_value={'choices': [{'message': {'content': json.dumps({'titles': ['New exhibition 0','New exhibition 1','New exhibition 2']})}}]}) as call, patch.object(self.backend.gl, 'save_json', side_effect=capture_save):
            self.backend.translate_job_titles('news', background=True)
            self.assertFalse(self.backend.CHAT_LOCK.locked())
            self.assertTrue(finished.wait(3))
            self.assertEqual(call.call_count, 1)
            self.assertNotIn(titles[3], self.backend.NEWS_TRANSLATIONS)

    def test_compact_brief_keeps_each_region_links_and_translations_without_image_metadata(self):
        rows = [{'title':f'Story {ring}-{i}', 'url':f'https://source.example/{ring}/{i}', 'ring':ring, 'source':'Publisher', 'lang':'en', 'image':'https://source.example/large-image.jpg'} for ring in range(4) for i in range(6)]
        with patch.dict(self.backend.CACHE, {'news':rows}):
            brief = self.backend.brief_news()
        self.assertEqual(len(brief), 16)
        self.assertEqual({row['ring'] for row in brief}, {0,1,2,3})
        self.assertTrue(all(row['url'].startswith('https://source.example/') for row in brief))
        self.assertTrue(all('image' not in row for row in brief))
        self.assertIn('image', rows[0])

    def test_brief_source_references_attach_only_original_known_links(self):
        rows = [{'url':'https://publisher.example/article_(original)'}, {'url':'https://other.example/story'}]
        text = 'A [translated headline][news-0]. Another [unknown][news-99].'
        result = self.backend.attach_brief_links(text, rows)
        self.assertIn('[news-0]: <https://publisher.example/article_(original)>', result)
        self.assertNotIn('[news-99]:', result)
        self.assertNotIn('https://other.example', result)
        self.assertEqual(rows[0]['url'], 'https://publisher.example/article_(original)')

    def test_ticketmaster_events_get_venue_pins_skip_cancelled_and_keep_the_key_out_of_the_cache(self):
        events = self.backend.event_sources
        today = self.backend.dt.date.today()
        day = (today + self.backend.dt.timedelta(days=3)).isoformat()
        venue = lambda city, code, lat, lon: {'_embedded': {'venues': [{'name': f'{city} Arena', 'city': {'name': city},
                                                       'country': {'name': city, 'countryCode': code}, 'location': {'latitude': str(lat), 'longitude': str(lon)}}]}}
        page = {'_embedded': {'events': [
            {'id': 'a', 'name': 'Concert in Trier', 'url': 'https://www.ticketmaster.de/event/a', 'dates': {'start': {'localDate': day, 'localTime': '20:00:00'}, 'status': {'code': 'onsale'}},
             'classifications': [{'segment': {'name': 'Music'}, 'genre': {'name': 'Rock'}}], 'priceRanges': [{'currency': 'EUR', 'min': 25, 'max': 40}], **venue('Trier', 'DE', 49.75, 6.64)},
            {'id': 'b', 'name': 'Cancelled show', 'url': 'https://www.ticketmaster.de/event/b', 'dates': {'start': {'localDate': day}, 'status': {'code': 'cancelled'}}, **venue('Berlin', 'DE', 52.5, 13.4)},
            {'id': 'c', 'name': 'Play in Vienna', 'url': 'https://www.ticketmaster.at/event/c', 'dates': {'start': {'localDate': day}, 'status': {'code': 'onsale'}},
             'classifications': [{'segment': {'name': 'Arts & Theatre'}}], **venue('Vienna', 'AT', 48.2, 16.37)}]}}
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            events.save_key(state, 'secret-consumer-key')
            calls = []
            fetch = lambda url, **_: calls.append(url) or page
            cache = events.refresh(state, {'lat': 49.7499, 'lon': 6.6371}, today, fetch=fetch, pause=0)
            self.assertEqual(len(calls), 1 + len(events.GERMANY) + len(events.EUROPE))
            self.assertEqual([(e['title'], e['area'], e['category'], e['price']) for e in cache['events']],
                             [('Concert in Trier', 'Trier', 'Music', '€25–€40'), ('Play in Vienna', 'Europe', 'Culture', 'Tickets on Ticketmaster')])
            self.assertEqual(cache['events'][0]['location']['lat'], 49.75)
            self.assertNotIn('secret-consumer-key', (state / 'live_events.json').read_text())
            events.refresh(state, {'lat': 49.7499, 'lon': 6.6371}, today, fetch=fetch, pause=0)
            self.assertEqual(len(calls), 1 + len(events.GERMANY) + len(events.EUROPE))  # cached for 12 hours
            merged = self.backend.discovery.upcoming_events(today, cache['events'])['items']
            self.assertIn('Concert in Trier', [row['title'] for row in merged])

    def test_ticketmaster_events_say_what_they_are_from_classification_lineup_and_notes(self):
        events = self.backend.event_sources
        today = self.backend.dt.date.today()
        base = {'url': 'https://www.ticketmaster.de/event/x', 'dates': {'start': {'localDate': today.isoformat()}},
                '_embedded': {'venues': [{'name': 'Uber Arena', 'city': {'name': 'Berlin'}, 'country': {'name': 'Germany', 'countryCode': 'DE'}}]}}
        home = {'lat': 49.75, 'lon': 6.64}
        def row(**fields):
            item = {**base, 'name': 'Show', **fields}
            item['_embedded'] = {**base['_embedded'], **fields.get('_embedded', {})}
            return events.normalize(item, home, today)
        acts = lambda *names: {'attractions': [{'name': n} for n in names]}
        concert = row(classifications=[{'segment': {'name': 'Music'}, 'genre': {'name': 'Rock'}, 'subGenre': {'name': 'Alternative Rock'}}],
                      _embedded=acts('Muse', 'Nova Twins'), info='Doors open at 18:00.', pleaseNote='No bags larger than A4.')
        self.assertEqual(concert['description'], 'Rock concert with Muse and Nova Twins at Uber Arena, Berlin.')
        self.assertEqual((concert['genre'], concert['subgenre'], concert['lineup'], concert['country_code']), ('Rock', 'Alternative Rock', ['Muse', 'Nova Twins'], 'DE'))
        self.assertEqual((concert['about'], concert['note']), ('Doors open at 18:00.', 'No bags larger than A4.'))
        match = row(classifications=[{'segment': {'name': 'Sports'}, 'genre': {'name': 'Soccer'}}], _embedded=acts('Hertha BSC', 'FC Schalke 04'))
        self.assertEqual(match['description'], 'Soccer match: Hertha BSC vs FC Schalke 04 at Uber Arena, Berlin.')
        musical = row(classifications=[{'segment': {'name': 'Arts & Theatre'}, 'genre': {'name': 'Musical'}}])
        self.assertEqual(musical['description'], 'Musical at Uber Arena, Berlin.')
        unknown = row(classifications=[{'segment': {'name': 'Undefined'}, 'genre': {'name': 'Undefined'}}])
        self.assertEqual((unknown['description'], unknown['genre'], unknown['about']), ('Event at Uber Arena, Berlin.', '', ''))

    def test_ticketmaster_cache_from_an_older_event_shape_refreshes_once(self):
        events = self.backend.event_sources
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            events.save_key(state, 'k')
            self.backend.gl.save_json(state / 'live_events.json', {'at': self.backend.time.time(), 'events': []})
            calls = []
            fetch = lambda url, **_: calls.append(url) or {}
            events.refresh(state, {'lat': 49.75, 'lon': 6.64}, self.backend.dt.date.today(), fetch=fetch, pause=0)
            self.assertEqual(len(calls), 1 + len(events.GERMANY) + len(events.EUROPE))
            events.refresh(state, {'lat': 49.75, 'lon': 6.64}, self.backend.dt.date.today(), fetch=fetch, pause=0)
            self.assertEqual(len(calls), 1 + len(events.GERMANY) + len(events.EUROPE))

    def test_brief_links_jobs_and_events_by_their_real_titles(self):
        jobs = [{'title': 'Werkstudent Data Science', 'url': 'https://jobs.example/1'}]
        events = [{'title': 'Autumn theatre', 'url': 'https://events.example/1'}]
        result = self.backend.attach_brief_links('- [Invented role][job-0]\n- Made up [Nope][job-7]\n- See [event-0]', [], jobs, events)
        self.assertIn('[Werkstudent Data Science][job-0]', result)
        self.assertIn('Made up Nope', result)
        self.assertIn('[Autumn theatre][event-0]', result)
        self.assertIn('[job-0]: <https://jobs.example/1>', result)
        self.assertNotIn('Invented role', result)

    def test_job_market_counts_roles_skills_experience_and_pay_from_postings(self):
        insights = self.backend.job_insights
        jobs = [{'id': '1', 'title': 'Werkstudent Data Science', 'flags': ['student-job'], 'city': 'Trier',
                 'text': 'Erste Erfahrungen mit Python und SQL. Vergütung: 15,50 € pro Stunde. R&D team.'},
                {'id': '2', 'title': 'Data Engineer', 'flags': [], 'city': 'Mainz',
                 'text': 'Seit 20 Jahren am Markt. You bring 3+ years of experience with Spark and Python. Salary €55,000 – €65,000 per year. Jobticket 49 €.'},
                {'id': '3', 'title': 'Datenanalyst', 'flags': [], 'city': 'Trier', 'text': ''}]
        market = insights.analyze(jobs, '## Skills\n- Strong: <e.g. Spark> Python, SQL\n- Learning: Spark\n## Other\nAWS')
        self.assertEqual([row['name'] for row in market['families']], ['Data science', 'Data engineering', 'Analytics & BI'])
        self.assertEqual([insights.family({'title': t}) for t in ('Flutter App Entwickler', 'Full Stack Developer', 'AI Engineer')], ['Mobile', 'Full stack & frontend', 'ML & AI'])
        self.assertEqual((market['total'], market['described']), (3, 2))
        self.assertEqual({row['name']: row['count'] for row in market['skills']}, {'Python': 2, 'SQL': 1, 'Spark': 1})
        self.assertEqual(market['gaps'], ['Spark'])
        self.assertEqual({row['name']: row['count'] for row in market['experience']['buckets']}, {'0–1 years': 0, '2–3 years': 1, '4–5 years': 0, '6+ years': 0})
        self.assertEqual((market['pay']['hourly']['median'], market['pay']['annual']['median']), (15.5, 60000))

    def test_market_cache_updates_when_description_contents_change_without_count_change(self):
        b = self.backend
        jobs = [{'id':'cache-test','title':'Engineer','flags':[], 'text':''}]
        with patch.dict(b.DESCRIPTIONS,{'cache-test':'Python'},clear=True), patch.dict(b._MARKET,{'key':None,'value':None}), \
                patch.object(b.gl,'read_profile',return_value=''), patch.object(b,'config',return_value={'jobs':{}}):
            first = b.job_market(jobs)
            b.DESCRIPTIONS['cache-test'] = 'SQL'
            second = b.job_market(jobs)
            self.assertEqual([r['name'] for r in first['skills']],['Python'])
            self.assertEqual([r['name'] for r in second['skills']],['SQL'])
            self.assertNotEqual(first['revision'],second['revision'])
            jobs[0]['skills'] = ['Docker']
            third = b.job_market(jobs)
            self.assertIn('Docker & Kubernetes',[r['name'] for r in third['skills']])

    def test_article_images_require_auth_and_only_serve_the_owned_cache(self):
        path = '/api/news/images/' + 'a' * 64
        with self.assertRaises(urllib.error.HTTPError) as result:
            urllib.request.urlopen(self.url + path)
        self.assertEqual(result.exception.code, 401)
        with patch.object(self.backend.NEWS_MEDIA, 'image', return_value=(b'cached-photo', 'image/jpeg')) as image:
            req = urllib.request.Request(self.url + path, headers={'X-Atlas-Token':self.backend.TOKEN})
            with urllib.request.urlopen(req) as response:
                self.assertEqual(response.read(), b'cached-photo')
                self.assertEqual(response.headers['Content-Type'], 'image/jpeg')
                self.assertIn('private', response.headers['Cache-Control'])
            image.assert_called_once_with('a' * 64)

    def test_news_keeps_real_publisher_feed_and_photo_and_separates_national_stories(self):
        items = [{'title':'A headline', 'link':'https://publisher.example/story', 'source':'The Publisher', 'source_url':'https://publisher.example', 'image':'https://publisher.example/photo.jpg', 'image_alt':'Photo credit'},
                 {'title':'National headline', 'link':'https://www.volksfreund.de/nachrichten/story', 'source':''}]
        with patch.object(self.backend.gl, 'http_get', return_value=b'feed'), patch.object(self.backend.gl, 'parse_feed', return_value=items):
            rows = self.backend.collect_news({'name':'Google News: Trier', 'url':'https://feed.example', 'ring':0})
        self.assertEqual(rows[0]['source'], 'The Publisher')
        self.assertEqual(rows[0]['feed'], 'Google News: Trier')
        self.assertEqual(rows[0]['image_alt'], 'Photo credit')
        self.assertEqual(rows[1]['ring'], 2)

    def test_map_home_uses_saved_config_coordinates_and_is_labelled_as_a_saved_base(self):
        state = self.backend.public_state()
        configured = self.backend.config()['home']
        self.assertEqual(state['home']['city'], configured['city'])
        self.assertEqual(state['home']['lat'], configured['lat'])
        self.assertEqual(state['home']['lon'], configured['lon'])
        self.assertEqual(state['home']['precision'], 'saved base')

    def test_update_install_waits_for_active_request(self):
        self.backend.CHAT_LOCK.acquire()
        try:
            with patch.object(self.backend.UPDATES, 'launch') as launch:
                with self.assertRaises(urllib.error.HTTPError) as result:
                    self.post('/api/updates/install', {})
                self.assertEqual(result.exception.code, 400)
                launch.assert_not_called()
        finally:
            self.backend.CHAT_LOCK.release()

    def test_update_build_blocks_new_ai_work_but_keeps_stop_available(self):
        with patch.object(self.backend.UPDATES, 'status', return_value={'phase': 'building', 'running': True}), patch.object(self.backend, 'stop_model') as stop:
            with self.assertRaises(urllib.error.HTTPError) as result:
                self.post('/api/brief', {})
            self.assertEqual(result.exception.code, 400)
            self.post('/api/model/stop', {}).close()
            stop.assert_called_once()

    def test_cross_origin_write_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as result:
            self.post('/api/profile', {'text': 'should not be saved'}, origin='https://example.com')
        self.assertEqual(result.exception.code, 403)
        self.assertIn('My profile', (self.project / 'profile.md').read_text())

    def test_real_deadline_saved_and_examples_ignored(self):
        self.post('/api/deadlines', {'title': 'Pay semester fee', 'date': '2027-02-03', 'category': 'uni'})
        rows = self.backend.public_state()['deadlines']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['title'], 'Pay semester fee')
        self.assertEqual(rows[0]['date'], '2027-02-03')

    def test_shift_updates_shared_work_budget(self):
        today = self.backend.gl.now(self.backend.gl.load_config()).date().isoformat()
        self.post('/api/work', {'employer': 'Atlas test', 'hours': 5, 'date': today, 'kind': 'regular'})
        self.assertEqual(self.backend.public_state()['work']['used'], 1)
        self.assertEqual(self.backend.public_state()['worklog'][0]['employer'], 'Atlas test')

    def test_invalid_shift_cannot_write(self):
        before = (self.project / 'data/worklog.csv').read_text()
        with self.assertRaises(urllib.error.HTTPError) as result:
            self.post('/api/work', {'employer': 'Atlas test', 'hours': -5, 'date': '2026-10-17'})
        self.assertEqual(result.exception.code, 400)
        self.assertEqual(before, (self.project / 'data/worklog.csv').read_text())

    def test_job_ratings_share_the_existing_index(self):
        self.backend.gl.save_json(self.project / 'data/jobs_index.json', {'J-12345': {'title': 'Data Analyst', 'company': 'Test role'}})
        self.post('/api/jobs/rate', {'id': 'J-12345', 'rating': 'up'})
        self.assertEqual(self.backend.public_state()['feedback']['J-12345']['rating'], 'up')
        self.post('/api/jobs/save', {'id': 'J-12345'})
        self.assertIn('J-12345', self.backend.public_state()['saved_jobs'])

    def test_state_survives_missing_worklog_and_broken_deadlines(self):
        data = self.project / 'data'
        (data / 'worklog.csv').rename(data / 'worklog.bak')
        good = (data / 'deadlines.toml').read_text()
        (data / 'deadlines.toml').write_text(good + '\n[[deadline]]\ntitle = "x"\ndate = "2026-13-01"\n')
        try:
            state = self.backend.public_state()
            self.assertEqual(state['work']['remaining'], state['work']['limit'])
            self.assertEqual(state['deadlines'], [])
            self.assertIn('deadlines.toml', state['deadlines_error'])
        finally:
            (data / 'worklog.bak').rename(data / 'worklog.csv')
            (data / 'deadlines.toml').write_text(good)

    def test_unsupported_reasoning_is_rejected(self):
        previous = self.backend.DATA['settings']['reasoning']
        with self.assertRaises(urllib.error.HTTPError):
            self.post('/api/settings', {'reasoning': 'made-up'})
        self.assertEqual(self.backend.DATA['settings']['reasoning'], previous)

    def test_translation_does_not_start_a_paused_model(self):
        with patch.object(self.backend, 'model_health', return_value=False), patch.object(self.backend, 'start_model') as start:
            for endpoint in ('/api/jobs/translate', '/api/news/translate'):
                with self.assertRaises(urllib.error.HTTPError) as result:
                    self.post(endpoint, {})
                self.assertEqual(result.exception.code, 400)
            start.assert_not_called()
            self.assertFalse(self.backend.CHAT_LOCK.locked())

    def test_headline_translation_uses_local_model_and_separate_persistent_cache(self):
        import io
        title = 'Neue Ausstellung im Stadtmuseum eröffnet'
        self.backend.CACHE['news'] = [{'title': title, 'lang': 'de'}]
        finished = threading.Event()
        save = self.backend.gl.save_json
        def capture_save(path, data):
            save(path, data)
            if path.name == 'news_translations.json':
                finished.set()
        with patch.object(self.backend, 'model_health', return_value=True), patch.object(self.backend.hermes_link, 'complete', return_value={'choices': [{'message': {'content': json.dumps({'titles': ['New exhibition opens at the city museum']})}}]}) as call, patch.object(self.backend.gl, 'save_json', side_effect=capture_save), patch.object(self.backend, 'start_model') as start:
            self.backend.translate_job_titles('news')
            self.assertTrue(finished.wait(3))
            self.assertEqual(call.call_args.args[0], self.backend.MODEL_ID)
            start.assert_not_called()
        self.assertEqual(json.loads((self.project / 'state/news_translations.json').read_text())[title], 'New exhibition opens at the city museum')
        self.assertNotIn(title, self.backend.TRANSLATIONS)

    def test_translation_worker_saves_local_model_result_by_original_title(self):
        title = 'Werkstudent für Nachhaltigkeitsforschung'
        self.backend.CACHE['jobs'] = [{'title': title, 'where': 'Trier'}]
        finished = threading.Event()
        save = self.backend.gl.save_json
        def capture_save(path, data):
            save(path, data)
            if path.name == 'job_translations.json':
                finished.set()
        with patch.object(self.backend, 'model_health', return_value=True), patch.object(self.backend.hermes_link, 'complete', return_value={'choices': [{'message': {'content': json.dumps({'titles': ['Working student in sustainability research']})}}]}) as call, patch.object(self.backend.gl, 'save_json', side_effect=capture_save):
            self.backend.translate_job_titles()
            self.assertTrue(finished.wait(3))
            self.assertEqual(call.call_args.args[0], self.backend.MODEL_ID)
        self.assertEqual(self.backend.TRANSLATIONS[title], 'Working student in sustainability research')

    def test_mensa_dishes_get_english_names_and_descriptions_from_the_local_model(self):
        b = self.backend
        menu = [{'canteen': 'Mensa Tarforst', 'open': True, 'meals': [{'name': 'Schokoladenpudding', 'category': 'Sweet Joker', 'student': 1.3}]}]
        finished = threading.Event()
        save = b.gl.save_json
        def capture_save(path, data):
            save(path, data)
            if path.name == 'mensa_translations.json':
                finished.set()
        reply = {'dishes': [{'name': 'Chocolate pudding', 'description': 'A sweet, creamy chocolate dessert.'}]}
        with patch.dict(b.CACHE, {'mensa_menu': menu}), patch.object(b, 'model_health', return_value=True), \
                patch.object(b.hermes_link, 'complete', return_value={'choices': [{'message': {'content': json.dumps(reply)}}]}), \
                patch.object(b.gl, 'save_json', side_effect=capture_save):
            self.assertEqual(b.pending_translations('mensa'), ['Schokoladenpudding'])
            b.api_post('/api/mensa/translate', {})
            self.assertTrue(finished.wait(3))
            meal = b.public_state()['mensa_menu'][0]['meals'][0]
        self.assertEqual((meal['name_en'], meal['student']), ('Chocolate pudding', 1.3))
        self.assertIn('chocolate dessert', meal['description'])
        self.assertEqual(b.MENSA_TRANSLATIONS['Schokoladenpudding']['name'], 'Chocolate pudding')

    def test_mensa_translation_rejects_incomplete_answers(self):
        reply = {'dishes': [{'name': 'Pizza', 'description': ' '}]}
        with patch.object(self.backend.hermes_link, 'complete', return_value={'choices': [{'message': {'content': json.dumps(reply)}}]}):
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                self.backend.translate_batch('mensa', ['Pizza Margherita'])

    def test_brief_never_shows_skill_frontmatter_and_dates_itself(self):
        b = self.backend
        skill = (SOURCE / 'skills/trier-morning-brief/SKILL.md').read_text()
        self.assertNotIn('name: trier-morning-brief', b.FRONTMATTER.sub('', skill, count=1))
        echoed = ('name: trier-morning-brief\ndescription: Turn the MORNING DATA block into a brief.\nversion: 0.2.0\n'
                  'metadata:\n  hermes:\n    tags: [germany]\n---\n\nTrier Morning Brief\n\n'
                  '☀️ **Wednesday, 2026-10-19**: today: overcast\n\n⏰ **Deadlines**: Visa on 2026-10-25\n\n**Trier**\n- Story [news-0]')
        result = b.finish_brief(echoed, b.dt.date(2026, 10, 19), ['today: overcast, 10–16 °C, rain chance 80%, wind up to 15 km/h'])
        self.assertTrue(result.startswith('🌧️ **Monday, 19 October 2026**: overcast, 10–16 °C, rain chance 80%'))
        self.assertNotIn('name:', result)
        self.assertNotIn('Wednesday', result)
        self.assertNotIn('Morning Brief', result)
        self.assertIn('**Deadlines**: Visa on 2026-10-25', result)
        self.assertTrue(b.brief_header(b.dt.date(2026, 10, 20), ['today: mainly clear, 8–14 °C, rain chance 5%']).startswith('🌤️ **Tuesday'))
        with patch.dict(b.DATA, {'brief': {'text': echoed, 'at': '2026-10-19T07:00:00+02:00'}}):
            self.assertTrue(b.public_state()['brief']['text'].startswith('Trier Morning Brief'))

    def test_brief_translates_its_german_picks_so_news_shows_the_same_headline(self):
        b = self.backend
        title = 'Immer mehr KI-Start-ups: Wie die Region Trier ins digitale Zeitalter startet'
        english = 'More and more AI startups: How the Trier region is launching into the digital age'
        news = [{'title': title, 'url': 'https://lokal.example/ki', 'source': 'Trierischer Volksfreund', 'ring': 0, 'lang': 'de'}]
        with patch.dict(b.CACHE, {'news': news}), patch.object(b.gl, 'save_json'), \
                patch.object(b.hermes_link, 'complete', return_value={'choices': [{'message': {'content': json.dumps({'titles': [english]})}}]}):
            b.translate_brief_headlines()
            picked = b.brief_news()
            self.assertEqual((picked[0]['title'], picked[0]['language']), (english, 'en'))
            self.assertEqual(b.public_state()['news'][0]['title_en'], english)
            linked = b.attach_brief_links('**Trier**:\n- KI-Startups boomen [news-0]', picked)
            self.assertIn(f'[{english}][news-0] · Trierischer Volksfreund', linked)

    def test_news_stories_can_be_saved_and_outlive_the_feed(self):
        b = self.backend
        story = {'title': 'Uni Trier startet ins Semester', 'url': 'https://lokal.example/semester', 'source': 'lokalo.de', 'ring': 0, 'lang': 'de',
                 'published': b.dt.datetime.now(b.dt.timezone.utc).isoformat()}
        with patch.dict(b.CACHE, {'news': [story]}), patch.dict(b.DATA, {'saved_news': []}), patch.object(b, 'persist'):
            self.assertTrue(b.api_post('/api/news/save', {'url': story['url']})['saved'])
            b.CACHE['news'] = []
            saved = b.public_state()['saved_news']
            self.assertEqual((saved[0]['url'], saved[0]['title']), (story['url'], story['title']))
            self.assertFalse(b.api_post('/api/news/save', {'url': story['url']})['saved'])
            self.assertEqual(b.public_state()['saved_news'], [])
            with self.assertRaisesRegex(ValueError, 'no longer in your news'):
                b.api_post('/api/news/save', {'url': story['url']})
            with self.assertRaisesRegex(ValueError, 'Choose a news story'):
                b.api_post('/api/news/save', {'url': 'javascript:alert(1)'})

    def test_stop_cancels_the_hermes_run_and_unloads_gemma_without_waiting_for_chat_lock(self):
        self.backend.CHAT_LOCK.acquire()
        try:
            with patch.object(self.backend, 'ACTIVE_RUN', 'run_busy'), patch.object(self.backend.hermes_link, 'stop_run') as stop_run, \
                    patch.object(self.backend.hermes_link, 'unload') as unload:
                self.post('/api/model/stop', {}).close()
                stop_run.assert_called_once_with('run_busy')
                unload.assert_called_once_with(self.backend.MODEL_ID)
                self.assertTrue(self.backend.CHAT_CANCEL.is_set())
                self.assertFalse(self.backend.MODEL_STOPPING.is_set())
        finally:
            self.backend.CHAT_LOCK.release()

    def test_cancelled_startup_cannot_launch_or_reload_model(self):
        self.backend.CHAT_CANCEL.set()
        with patch.object(self.backend.GATEWAY, 'start') as start, patch.object(self.backend.hermes_link, 'load') as load:
            with self.assertRaisesRegex(RuntimeError, 'cancelled'):
                self.backend.start_model(wait=True)
            start.assert_not_called()
            load.assert_not_called()
        self.backend.CHAT_CANCEL.clear()

    def test_chat_turns_continue_one_hermes_session_and_stream_its_events(self):
        events = [{'event': 'message.delta', 'text': 'Hel'}, {'event': 'tool.started', 'tool': 'web_search'},
                  {'event': 'run.completed', 'output': 'Hello, Dhiraj.', 'usage': {'total_tokens': 9}}]
        session = self.backend.DATA['settings']['hermes_session']
        with patch.object(self.backend, 'start_model'), patch.object(self.backend.hermes_link, 'create_run', return_value='run_1') as create, \
                patch.object(self.backend.hermes_link, 'run_events', side_effect=lambda run: iter(events)):
            for text in ('Hi', 'Again'):
                self.backend.CHAT_LOCK.acquire()
                self.backend.DATA['chat'].append({'id': text, 'role': 'assistant', 'text': '', 'status': 'loading', 'tools': []})
                self.backend.chat_worker(text, text, 'chat')
                row = self.backend.DATA['chat'][-1]
                self.assertEqual((row['status'], row['text'], row['tools']), ('done', 'Hello, Dhiraj.', ['web_search']))
        self.assertEqual([call.kwargs['session_id'] for call in create.call_args_list], [session, session])
        self.assertEqual(create.call_args.kwargs['model'], self.backend.MODEL_ID)

    def test_gemma_unloads_after_five_idle_minutes_but_not_during_a_routine(self):
        now = 10_000.0
        with patch.object(self.backend, 'model_health', return_value=True), patch.object(self.backend.hermes_link, 'unload') as unload, \
                patch.object(self.backend.hermes_link, 'busy', return_value=True):
            self.backend.ACTIVITY['at'] = now - 299
            self.assertFalse(self.backend.idle_unload(now))
            self.backend.ACTIVITY['at'] = now - 301
            self.assertFalse(self.backend.idle_unload(now))  # a routine is generating: that counts as use
            self.assertEqual(self.backend.ACTIVITY['at'], now)
            with patch.object(self.backend.hermes_link, 'busy', return_value=False):
                self.assertTrue(self.backend.idle_unload(now + 301))
        unload.assert_called_once_with(self.backend.MODEL_ID)


if __name__ == '__main__':
    unittest.main()
