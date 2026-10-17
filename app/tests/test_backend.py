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

    def test_unsupported_reasoning_is_rejected(self):
        with self.assertRaises(urllib.error.HTTPError):
            self.post('/api/settings', {'reasoning': 'made-up'})
        self.assertEqual(self.backend.DATA['settings']['reasoning'], 'medium')

    def test_translation_does_not_start_a_paused_model(self):
        with patch.object(self.backend, 'model_health', return_value=False), patch.object(self.backend, 'start_model') as start:
            with self.assertRaises(urllib.error.HTTPError) as result:
                self.post('/api/jobs/translate', {})
            self.assertEqual(result.exception.code, 400)
            start.assert_not_called()
            self.assertFalse(self.backend.CHAT_LOCK.locked())

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
