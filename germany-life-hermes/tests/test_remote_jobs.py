"""Public remote provider contracts and outage behavior without network access."""
import datetime as dt
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import gl_common as gl
import remote_boards as providers
import job_scan


class RemoteJobsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'GERMANY_LIFE_HOME': self.tmp.name})
        self.env.start()
        self.today = dt.datetime.now(dt.timezone.utc)
        self.cfg = {'jobs': {'include': ['data'], 'max_age_days': 14, 'remote': {'remotive_categories': [], 'himalayas_queries':['data'], 'jobicy_industries':['data-science'], 'jobicy_geos':['europe']}}}
        self.matcher = job_scan.Matcher(self.cfg['jobs'])
        self.himalayas = {'guid':'h1','title':'Data Scientist','companyName':'Team',
                         'applicationLink':'https://himalayas.app/companies/team/jobs/data',
                         'pubDate':self.today.timestamp(), 'expiryDate':(self.today + dt.timedelta(days=10)).timestamp()*1000,
                         'locationRestrictions':[{'name':'Germany','alpha2':'DE'},'France'],
                         'timezoneRestrictions':[1,2], 'description':'<p>Build data tools</p>'}
        self.remoteok = {'id':'r1','position':'Data Analyst','company':'Team',
                         'date':self.today.isoformat(),'url':'https://remoteok.com/remote-jobs/r1'}
        self.jobicy = {'id':123,'jobTitle':'Data Engineer','companyName':'Team',
                       'pubDate':self.today.isoformat(),'url':'https://jobicy.com/jobs/123', 'jobGeo':'Europe'}

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def fetch(self, status=None):
        return providers.fetch_remote(self.cfg, {2,3}, self.matcher, status if status is not None else [])

    def test_three_schemas_attribution_restrictions_and_dates(self):
        for provider, item in [('himalayas',self.himalayas),('remoteok',self.remoteok),('jobicy',self.jobicy)]:
            job = getattr(providers,provider)(item)
            self.assertTrue(job['remote'])
            self.assertIn(job['ring'],{2,3})
            self.assertEqual(job['city'],'Remote')
            self.assertEqual(job['posted'],self.today.date().isoformat())
            self.assertTrue(job['url'].startswith('https://'))
        job = providers.himalayas(self.himalayas)
        self.assertIn('Germany, France',job['where'])
        self.assertIn('Timezones: 1, 2',job['region_name'])
        self.assertEqual(job['text'],'Build data tools')
        self.assertEqual(providers.remote_date(self.today.timestamp()*1000)[:10],self.today.date().isoformat())

    def test_metadata_unsafe_links_expired_and_malformed_jobs_are_skipped(self):
        for item in [None, {'legal':'API attribution'}, {**self.remoteok,'url':'javascript:alert(1)'}, {**self.remoteok,'position':''}]:
            self.assertIsNone(providers.remoteok(item))
        self.assertIsNone(providers.himalayas({**self.himalayas,'expiryDate':(self.today-dt.timedelta(days=1)).isoformat()}))

    def test_keyless_requests_cache_daily_filter_old_roles_and_deduplicate(self):
        old = {**self.jobicy,'id':124,'pubDate':(self.today-dt.timedelta(days=30)).isoformat()}
        unrelated = {**self.jobicy,'id':125,'jobTitle':'Sales Manager'}
        responses = {'himalayas':{'jobs':[self.himalayas]}, 'remoteok':[{'legal':'attribution'},self.remoteok], 'jobicy':{'jobs':[self.jobicy,self.jobicy,old,unrelated]}}
        with patch.object(gl,'http_json',side_effect=lambda url, **_: next(value for name,value in responses.items() if name in url)) as request:
            self.assertEqual(len(self.fetch()),3)
            self.assertEqual(len(self.fetch()),3)
            self.assertEqual(request.call_count,3)
            self.assertTrue(all('headers' not in call.kwargs for call in request.call_args_list))

    def test_outage_uses_saved_rows_and_backs_off_even_on_bad_schema(self):
        path = gl.state_dir() / 'remote_boards_cache.json'
        url = 'https://himalayas.app/jobs/api/search?q=data&country=DE&sort=recent'
        gl.save_json(path,{url:{'at':1,'data':{'jobs':[self.himalayas]}}})
        self.cfg['jobs']['remote'].update(remoteok=False,jobicy_industries=[])
        status=[]
        with patch.object(gl,'http_json',return_value={'error':'unavailable'}) as request:
            self.assertEqual(len(self.fetch(status)),1)
            self.assertEqual(len(self.fetch()),1)
            self.assertEqual(request.call_count,1)
        self.assertIn('Himalayas 1',status[0])

    def test_local_scans_and_disabled_providers_make_no_requests(self):
        with patch.object(gl,'http_json') as request:
            self.assertEqual(providers.fetch_remote(self.cfg,{0,1},self.matcher,[]),[])
            self.cfg['jobs']['remote'] = {'enabled':False}
            self.assertEqual(self.fetch(),[])
            request.assert_not_called()
