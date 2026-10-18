"""Provider contracts and shared request limits, with no external requests."""
import datetime as dt
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import gl_common as gl
import job_providers as providers
import job_scan


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"GERMANY_LIFE_HOME": self.tmp.name, "JSEARCH_API_KEY": "", "JSEARCH_HOST": "openwebninja"})
        self.env.start()
        self.search = {"what": "Data Scientist", "where": "Trier", "country": "de", "radius_km": 50}
        self.item = {"job_id": "test-job", "job_title": "Working Student Data Science", "employer_name": "Test company",
                     "job_country": "DE", "job_location": "Trier • via Publisher", "job_is_remote": True,
                     "job_posted_at_datetime_utc": dt.date.today().isoformat(), "job_description": "Python and SQL",
                     "job_apply_link": "https://publisher.example/job", "apply_options": [
                         {"is_direct": True, "apply_link": "javascript:alert(1)"},
                         {"is_direct": True, "apply_link": "https://employer.example/job"}]}

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_credentials_owner_only_never_in_public_state_and_disconnect_overrides_environment(self):
        providers.save_credentials("openwebninja", "private-test-key")
        self.assertEqual((gl.state_dir() / "job_credentials.json").stat().st_mode & 0o777, 0o600)
        self.assertTrue(providers.provider_state()["configured"])
        self.assertNotIn("private-test-key", json.dumps(providers.provider_state()))
        providers.save_credentials("openwebninja", "")
        with patch.dict(os.environ, {"JSEARCH_API_KEY": "environment-key"}):
            self.assertFalse(providers.provider_state()["configured"])

    def test_saved_credentials_survive_a_fresh_process_without_returning_the_key(self):
        providers.save_credentials('openwebninja','private-restart-test-key')
        script = '''import json, sys
sys.path.insert(0, sys.argv[1])
import job_providers
assert job_providers.credentials() == ('openwebninja', 'private-restart-test-key')
print(json.dumps(job_providers.provider_state()))
'''
        result = subprocess.check_output([sys.executable,'-c',script,str(Path(providers.__file__).parent)],text=True)
        self.assertTrue(json.loads(result)['configured'])
        self.assertNotIn('private-restart-test-key',result)

    def test_both_provider_response_shapes_and_header_authentication(self):
        for host, response, header in [("openwebninja", {"data": {"jobs": [self.item], "cursor": "ignored"}}, "x-api-key"),
                                       ("rapidapi", {"data": [self.item]}, "x-rapidapi-key")]:
            with patch.object(gl, "http_json", return_value=response) as request:
                raw, cached = providers.search_jsearch(self.search, "secret", host, 14)
                self.assertFalse(cached)
                self.assertEqual(raw, [self.item])
                url = request.call_args.args[0]
                params = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
                self.assertEqual(params["country"], ["de"])
                self.assertEqual(params["radius"], ["50"])
                self.assertNotIn("secret", url)
                self.assertEqual(request.call_args.kwargs["headers"][header], "secret")

    def test_repeated_search_uses_cache_even_across_calls_and_countrywide_omits_radius(self):
        search = {"what": "Data Scientist", "where": "Germany", "country": "de"}
        with patch.object(gl, "http_json", return_value={"data": {"jobs": [self.item]}}) as request:
            providers.search_jsearch(search, "secret", "openwebninja", 14)
            _, cached = providers.search_jsearch(search, "secret", "openwebninja", 14)
            self.assertTrue(cached)
            self.assertEqual(request.call_count, 1)
            self.assertNotIn("radius=", request.call_args.args[0])
            self.assertEqual(providers.provider_state()["requests"], 1)

    def test_budget_reserves_failed_requests_and_stops_at_monthly_cap(self):
        with patch.object(gl, "http_json", side_effect=urllib.error.HTTPError("https://api.example", 429, "rate limit", {}, None)) as request:
            with self.assertRaises(ValueError):
                providers.search_jsearch(self.search, "secret", "openwebninja", 14)
            with self.assertRaises(ValueError):
                providers.search_jsearch(self.search, "secret", "openwebninja", 14)
            self.assertEqual(request.call_count, 1)
        self.assertEqual(providers.provider_state()["requests"], 1)
        gl.save_json(gl.state_dir() / "jsearch_cache.json", {"month": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m"), "requests": 180})
        with patch.object(gl, "http_json") as request:
            with self.assertRaisesRegex(ValueError, "monthly"):
                providers.search_jsearch(self.search, "different", "openwebninja", 14)
            request.assert_not_called()

    def test_new_month_resets_budget_and_bad_schema_does_not_cache_empty_success(self):
        gl.save_json(gl.state_dir() / "jsearch_cache.json", {"month": "2000-01", "requests": 180})
        with patch.object(gl, "http_json", return_value={"status": "ERROR"}):
            with self.assertRaises(ValueError):
                providers.search_jsearch(self.search, "secret", "openwebninja", 14)
        self.assertEqual(providers.provider_state()["requests"], 1)
        self.assertEqual(gl.load_json(gl.state_dir() / "jsearch_cache.json", {})["queries"], {})

    def test_normalizes_direct_links_null_fields_and_rejects_unusable_jobs(self):
        job = providers.normalize_jsearch(self.item, 1)
        self.assertEqual(job["url"], "https://employer.example/job")
        self.assertEqual(job["city"], "Trier")
        self.assertTrue(job["remote"])
        self.assertIsNone(providers.normalize_jsearch({"job_title": "No id"}, 0))
        self.assertIsNone(providers.normalize_jsearch({"job_id": "x", "job_title": "Data", "job_apply_link": "file:///tmp/secret"}, 0))
        job = providers.normalize_jsearch({**self.item, "apply_options": None, "job_city": None, "job_description": None}, 0)
        self.assertEqual(job["text"], "")

    def test_matching_dates_duplicates_and_rings(self):
        providers.save_credentials("openwebninja", "secret")
        old = {**self.item, "job_id": "old", "job_posted_at_datetime_utc": "2000-01-01"}
        irrelevant = {**self.item, "job_id": "other", "job_title": "Chef"}
        cfg = {"jobs": {"include": ["data"], "jsearch": {"searches": [{**self.search, "ring": 1}, {**self.search, "ring": 3}]}}}
        with patch.object(gl, "http_json", return_value={"data": {"jobs": [self.item, self.item, old, irrelevant]}}):
            status = []
            jobs = providers.fetch_jsearch(cfg, {1}, job_scan.Matcher(cfg["jobs"]), status, allow_network=True)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["ring"], 1)
        self.assertTrue(status[0].startswith("✓"))

    def test_automatic_scan_without_cache_never_contacts_provider_or_reserves_credits(self):
        providers.save_credentials('openwebninja','secret')
        cfg={'jobs':{'include':['data'],'jsearch':{'enabled':True,'searches':[self.search]}}}
        with patch.object(gl,'http_json') as request:
            status=[]
            jobs=providers.fetch_jsearch(cfg,{2},job_scan.Matcher(cfg['jobs']),status)
        request.assert_not_called()
        self.assertEqual(jobs,[])
        self.assertEqual(providers.provider_state()['requests'],0)
        self.assertIn('no credits used',status[0])
        self.assertFalse((gl.state_dir()/'jsearch_cache.json').exists())

    def test_automatic_scan_uses_old_cache_without_changing_request_budget(self):
        providers.save_credentials('openwebninja','secret')
        with patch.object(gl,'http_json',return_value={'data':{'jobs':[self.item]}}):
            providers.search_jsearch(self.search,'secret','openwebninja',14)
        cache=gl.state_dir()/'jsearch_cache.json'
        before=cache.read_bytes()
        cfg={'jobs':{'include':['data'],'jsearch':{'enabled':False,'searches':[self.search]}}}
        with patch.object(providers.time,'time',return_value=providers.time.time()+2*86400), patch.object(gl,'http_json') as request:
            jobs=providers.fetch_jsearch(cfg,{2},job_scan.Matcher(cfg['jobs']),[])
        request.assert_not_called()
        self.assertEqual(len(jobs),1)
        self.assertEqual(cache.read_bytes(),before)
        self.assertEqual(providers.provider_state()['requests'],1)

    def test_explicit_manual_search_can_fetch_with_legacy_automatic_switch_disabled(self):
        providers.save_credentials('openwebninja','secret')
        cfg={'jobs':{'include':['data'],'jsearch':{'enabled':False,'searches':[self.search]}}}
        with patch.object(gl,'http_json',return_value={'data':{'jobs':[self.item]}}) as request:
            jobs=providers.fetch_jsearch(cfg,{2},job_scan.Matcher(cfg['jobs']),[],allow_network=True)
        self.assertEqual(len(jobs),1)
        self.assertEqual(request.call_count,1)
        self.assertEqual(providers.provider_state()['requests'],1)

    def test_bundesagentur_details_uses_base64_reference_and_public_client_header(self):
        with patch.object(gl, "http_json", return_value={"stellenangebotsBeschreibung": "<p>Full requirements</p>"}) as request:
            self.assertEqual(providers.bundesagentur_description("10000-test-S"), "Full requirements")
        self.assertIn("/pc/v4/jobdetails/MTAwMDAtdGVzdC1T", request.call_args.args[0])
        self.assertEqual(request.call_args.kwargs["headers"]["X-API-Key"], "jobboerse-jobsuche")
