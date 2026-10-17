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

    def test_briefs_use_fresh_tool_free_hermes_and_chat_keeps_its_tools(self):
        brief = self.backend.hermes_arguments('brief')
        self.assertEqual(brief[brief.index('--model')+1], 'atlas-local')
        self.assertEqual(brief[brief.index('--reasoning')+1], 'none')
        self.assertEqual(brief[brief.index('--toolsets')+1], 'none')
        self.assertEqual(brief[brief.index('--max-turns')+1], '1')
        self.assertNotIn('--continue', brief)
        self.assertNotIn('--resume', brief)
        chat = self.backend.hermes_arguments('chat')
        self.assertNotIn('--continue', chat)
        self.assertNotIn('--resume', chat)
        self.assertEqual(chat[chat.index('--toolsets')+1], 'terminal,skills,memory,web')

    def test_recent_chat_is_bounded_and_omits_failed_and_brief_messages(self):
        rows = [{'id':'old', 'role':'user', 'text':'a' * 6000},
                {'id':'b', 'role':'assistant', 'text':'A long brief', 'kind':'brief'},
                {'id':'a', 'role':'user', 'text':'Call me Alex'},
                {'id':'e', 'role':'assistant', 'text':'Failure', 'status':'error'},
                {'id':'u', 'role':'user', 'text':'What is my name?'},
                {'id':'current', 'role':'assistant', 'text':''}]
        with patch.dict(self.backend.DATA, {'chat':rows}):
            self.assertEqual(self.backend.recent_chat('current'), [{'role':'user', 'text':'Call me Alex'}])

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

    def test_background_translation_leaves_chat_available_and_saves_only_one_batch(self):
        import io
        titles = [f'Neue Ausstellung Nummer {i}' for i in range(5)]
        response = io.BytesIO(json.dumps({'choices':[{'message':{'content':json.dumps({'titles':['New exhibition 0','New exhibition 1','New exhibition 2']})}}]}).encode())
        key = self.project / 'test-background.key'
        key.write_text('test-key')
        finished = threading.Event()
        save = self.backend.gl.save_json
        def capture_save(path, value):
            save(path, value)
            if path.name == 'news_translations.json':
                finished.set()
        with patch.dict(self.backend.CACHE, {'news':[{'title':t, 'lang':'de'} for t in titles]}), patch.object(self.backend, 'model_health', return_value=True), patch.object(self.backend, 'MODEL_KEY_FILE', key), patch.object(self.backend.urllib.request, 'urlopen', return_value=response) as call, patch.object(self.backend.gl, 'save_json', side_effect=capture_save):
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
        response = io.BytesIO(json.dumps({'choices': [{'message': {'content': json.dumps({'titles': ['New exhibition opens at the city museum']})}}]}).encode())
        key = self.project / 'test-news-model.key'
        key.write_text('test-key')
        finished = threading.Event()
        save = self.backend.gl.save_json
        def capture_save(path, data):
            save(path, data)
            if path.name == 'news_translations.json':
                finished.set()
        with patch.object(self.backend, 'model_health', return_value=True), patch.object(self.backend, 'MODEL_KEY_FILE', key), patch.object(self.backend.urllib.request, 'urlopen', return_value=response) as call, patch.object(self.backend.gl, 'save_json', side_effect=capture_save), patch.object(self.backend, 'start_model') as start:
            self.backend.translate_job_titles('news')
            self.assertTrue(finished.wait(3))
            self.assertEqual(call.call_args.args[0].full_url, self.backend.MODEL_URL + '/v1/chat/completions')
            start.assert_not_called()
        self.assertEqual(json.loads((self.project / 'state/news_translations.json').read_text())[title], 'New exhibition opens at the city museum')
        self.assertNotIn(title, self.backend.TRANSLATIONS)

    def test_translation_worker_saves_local_model_result_by_original_title(self):
        title = 'Werkstudent für Nachhaltigkeitsforschung'
        self.backend.CACHE['jobs'] = [{'title': title, 'where': 'Trier'}]
        import io
        response = io.BytesIO(json.dumps({'choices': [{'message': {'content': json.dumps({'titles': ['Working student in sustainability research']})}}]}).encode())
        key = self.project / 'test-model.key'
        key.write_text('test-key')
        finished = threading.Event()
        save = self.backend.gl.save_json
        def capture_save(path, data):
            save(path, data)
            if path.name == 'job_translations.json':
                finished.set()
        with patch.object(self.backend, 'model_health', return_value=True), patch.object(self.backend, 'MODEL_KEY_FILE', key), patch.object(self.backend.urllib.request, 'urlopen', return_value=response) as call, patch.object(self.backend.gl, 'save_json', side_effect=capture_save):
            self.backend.translate_job_titles()
            self.assertTrue(finished.wait(3))
            self.assertEqual(call.call_args.args[0].full_url, self.backend.MODEL_URL + '/v1/chat/completions')
        self.assertEqual(self.backend.TRANSLATIONS[title], 'Working student in sustainability research')

    def test_stopping_model_persists_pause_across_app_restarts(self):
        with patch.object(self.backend, 'terminate_owned_process'):
            self.post('/api/model/stop', {})
        self.assertFalse(self.backend.DATA['settings']['model_autostart'])
        saved = json.loads(self.backend.STORE.read_text())
        self.assertFalse(saved['settings']['model_autostart'])

    def test_stop_terminates_busy_agent_and_model_without_waiting_for_chat_lock(self):
        agent = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True)
        model = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True)
        self.backend.CHAT_LOCK.acquire()
        try:
            with patch.object(self.backend, 'CHAT_PROCESS', agent), patch.object(self.backend, 'MODEL_PROCESS', model):
                self.post('/api/model/stop', {}).close()
                self.assertIsNotNone(agent.poll())
                self.assertIsNotNone(model.poll())
                self.assertIsNone(self.backend.MODEL_PROCESS)
                self.assertTrue(self.backend.CHAT_CANCEL.is_set())
                self.assertFalse(self.backend.DATA['settings']['model_autostart'])
                self.assertFalse(self.backend.MODEL_STOPPING.is_set())
        finally:
            self.backend.CHAT_LOCK.release()
            for proc in (agent, model):
                if proc.poll() is None:
                    proc.kill()
                proc.wait()

    def test_cancelled_startup_cannot_launch_or_reload_model(self):
        self.backend.CHAT_CANCEL.set()
        with patch.object(self.backend.subprocess, 'Popen') as launch:
            with self.assertRaisesRegex(RuntimeError, 'cancelled'):
                self.backend.start_model(wait=True)
            launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
