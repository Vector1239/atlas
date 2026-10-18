"""Offline tests: parsers, filters, dedupe and the data tools, with the network faked.

Run with ./gl test. These check the logic only; ./gl check tests the real sources.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import gl_common as gl  # noqa: E402
import deadlines  # noqa: E402
import glctl  # noqa: E402
import job_scan  # noqa: E402
import morning_brief  # noqa: E402

TODAY = dt.date.today()
NOW_RFC822 = dt.datetime.now(dt.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
OLD_RFC822 = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=9)).strftime("%a, %d %b %Y %H:%M:%S +0000")

RSS = f"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Neue Mensa in Trier eröffnet - Volksfreund</title><link>https://example.org/a</link>
<pubDate>{NOW_RFC822}</pubDate><source url="https://volksfreund.de">Volksfreund</source>
<description>&lt;p&gt;Die &lt;b&gt;neue&lt;/b&gt; Mensa&amp;nbsp;öffnet.&lt;/p&gt;</description></item>
<item><title>Old story</title><link>https://example.org/old</link><pubDate>{OLD_RFC822}</pubDate></item>
</channel></rss>""".encode()

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Moving to Trier, tips?</title><link rel="alternate" href="https://reddit.com/r/Trier/x"/>
<updated>2026-10-16T08:00:00+00:00</updated><content type="html">&lt;p&gt;hi&lt;/p&gt;</content></entry></feed>"""

RDF = b"""<?xml version="1.0"?><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/">
<item><title>Germany changes Blue Card rules</title><link>https://dw.com/x</link>
<dc:date>2026-10-16T09:00:00Z</dc:date></item></rdf:RDF>"""

BA = {"stellenangebote": [
    {"titel": "Werkstudent Data Analytics (m/w/d)", "beruf": "Data Analyst", "refnr": "10000-1",
     "arbeitgeber": "Trier Tech GmbH", "aktuelleVeroeffentlichungsdatum": TODAY.isoformat(),
     "arbeitsort": {"ort": "Trier", "region": "Rheinland-Pfalz", "entfernung": "2"}},
    {"titel": "Senior Data Scientist", "beruf": "Data Scientist", "refnr": "10000-2",
     "arbeitgeber": "Big Corp", "aktuelleVeroeffentlichungsdatum": TODAY.isoformat(),
     "arbeitsort": {"ort": "Saarbrücken", "entfernung": "80"}},
    {"titel": "Datenschutzbeauftragter", "beruf": "Jurist", "refnr": "10000-3",
     "arbeitgeber": "X", "arbeitsort": {"ort": "Trier"}},
    {"titel": "Lagerhelfer", "beruf": "Lager", "refnr": "10000-4", "arbeitgeber": "Y",
     "arbeitsort": {"ort": "Trier"}},
]}

ENGLISH = ("We are looking for a working student to join our data team. You will work with "
           "Python and SQL and you will help our analysts with the dashboards for our customers "
           "in the region. We offer flexible hours and you can work from home.")

ARBEITNOW = {"data": [
    {"slug": "ml-intern-lux", "company_name": "LuxAI", "title": "Machine Learning Intern",
     "description": f"<p>{ENGLISH}</p>", "remote": False, "url": "https://arbeitnow.com/ml-intern-lux",
     "tags": ["AI"], "job_types": ["internship"], "location": "Luxembourg",
     "created_at": int(dt.datetime.now(dt.timezone.utc).timestamp())},
    {"slug": "chef-berlin", "company_name": "Food", "title": "Chef", "description": "", "remote": False,
     "url": "u", "tags": [], "job_types": [], "location": "Berlin",
     "created_at": int(dt.datetime.now(dt.timezone.utc).timestamp())},
], "links": {}, "meta": {}}

WEATHER = {"daily": {"weather_code": [61, 3], "temperature_2m_max": [14.2, 12.0],
                     "temperature_2m_min": [7.1, 6.0], "precipitation_probability_max": [70, 20],
                     "wind_speed_10m_max": [21.0, 10.0]}}
CANTEENS = [{"id": 42, "name": "Trier, Mensa Tarforst", "city": "Trier"},
            {"id": 7, "name": "Luxembourg Campus", "city": "Esch"}]
MEALS = [{"name": "Gemüsecurry", "category": "Vegan", "prices": {"students": 2.9}}]


class FakeNet:
    """Answers http_get / http_json from a URL-substring table."""

    def __init__(self, routes: dict, fail: tuple = ()):
        self.routes, self.fail, self.calls = routes, fail, []

    def get(self, url, headers=None, timeout=20):
        self.calls.append((url, headers or {}))
        if any(part in url for part in self.fail):
            raise urllib.error.URLError("blocked in test")
        for part, body in self.routes.items():
            if part in url:
                return body if isinstance(body, bytes) else json.dumps(body).encode()
        raise urllib.error.HTTPError(url, 404, "not found", {}, None)

    def json(self, url, headers=None, timeout=20):
        return json.loads(self.get(url, headers, timeout).decode())


class ProjectCase(unittest.TestCase):
    """Each test gets a fresh copy of the project config in a temp folder."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(ROOT / "config", self.tmp / "config")
        (self.tmp / "data").mkdir()
        shutil.copy(ROOT / "templates" / "profile.md", self.tmp / "profile.md")
        shutil.copy(ROOT / "templates" / "deadlines.toml", self.tmp / "data" / "deadlines.toml")
        self._env = os.environ.get("GERMANY_LIFE_HOME")
        os.environ["GERMANY_LIFE_HOME"] = str(self.tmp)
        self._get, self._json = gl.http_get, gl.http_json

    def tearDown(self):
        gl.http_get, gl.http_json = self._get, self._json
        if self._env is None:
            os.environ.pop("GERMANY_LIFE_HOME", None)
        else:
            os.environ["GERMANY_LIFE_HOME"] = self._env
        shutil.rmtree(self.tmp)

    def use_net(self, net: FakeNet):
        gl.http_get, gl.http_json = net.get, net.json
        return net


class FeedTests(unittest.TestCase):
    def test_article_images_from_media_rss_enclosures_and_html_stay_with_their_story(self):
        xml = b'''<rss xmlns:media="http://search.yahoo.com/mrss/"><channel>
        <item><title>Enclosure</title><link>https://paper.example/a</link><source url="https://paper.example">The Paper</source><enclosure url="https://paper.example/a.jpg" type="image/jpeg"/></item>
        <item><title>Media</title><media:group><media:content url="https://paper.example/b.jpg" medium="image"/></media:group></item>
        <item><title>HTML</title><description>&lt;p&gt;&lt;img src="https://paper.example/c.jpg" alt="Photo credit"/&gt;Story&lt;/p&gt;</description></item>
        </channel></rss>'''
        rows = gl.parse_feed(xml)
        self.assertEqual([row['image'] for row in rows], ['https://paper.example/a.jpg', 'https://paper.example/b.jpg', 'https://paper.example/c.jpg'])
        self.assertEqual(rows[0]['source_url'], 'https://paper.example')
        self.assertEqual(rows[2]['image_alt'], 'Photo credit')
        self.assertEqual(rows[2]['summary'], 'Story')

    def test_rss_atom_rdf(self):
        rss = gl.parse_feed(RSS)
        self.assertEqual(rss[0]["title"], "Neue Mensa in Trier eröffnet - Volksfreund")
        self.assertEqual(rss[0]["source"], "Volksfreund")
        self.assertEqual(rss[0]["summary"], "Die neue Mensa öffnet.")
        self.assertIsNotNone(rss[0]["published"].tzinfo)
        atom = gl.parse_feed(ATOM)
        self.assertEqual(atom[0]["link"], "https://reddit.com/r/Trier/x")
        rdf = gl.parse_feed(RDF)
        self.assertEqual(rdf[0]["published"].year, 2026)

    def test_clean_text_strips_invisible(self):
        self.assertEqual(gl.clean_text("a​b  <i>c</i>", 10), "ab c")
        self.assertEqual(gl.clean_text("x" * 20, 5), "xxxx…")

    def test_language_guess(self):
        self.assertTrue(gl.looks_english(ENGLISH))
        self.assertIsNone(gl.looks_english("too short"))


class JobScanTests(ProjectCase):
    def routes(self):
        return {"arbeitsagentur": BA, "arbeitnow": ARBEITNOW}

    def test_bundesagentur_current_response(self):
        self.use_net(FakeNet({"arbeitsagentur": {"ergebnisliste": [{
            "stellenangebotsTitel": "Werkstudent Data Analytics",
            "referenznummer": "10000-current-S", "firma": "Trier Tech",
            "stellenlokationen": [{"adresse": {"ort": "Trier", "region": "Rheinland-Pfalz"}}],
            "entfernung": 2, "homeofficemoeglich": True,
            "veroeffentlichungszeitraum": {"von": TODAY.isoformat()},
        }]}}))
        status = []
        cfg = gl.load_config()
        jobs = job_scan.fetch_bundesagentur(cfg, {0}, job_scan.Matcher(cfg["jobs"]), status)
        self.assertTrue(jobs)
        self.assertEqual(jobs[0]["title"], "Werkstudent Data Analytics")
        self.assertEqual(jobs[0]["company"], "Trier Tech")
        self.assertEqual(jobs[0]["where"], "Trier, Rheinland-Pfalz (2 km)")
        self.assertEqual(jobs[0]["posted"], TODAY.isoformat())
        self.assertTrue(jobs[0]["remote"])
        self.assertTrue(jobs[0]["url"].endswith("/10000-current-S"))

    def test_filters_flags_and_dedupe_across_runs(self):
        net = self.use_net(FakeNet(self.routes()))
        first = job_scan.run({0, 1}, dry_run=False)
        self.assertIn("Werkstudent Data Analytics", first)
        self.assertIn("Machine Learning Intern", first)
        self.assertNotIn("Datenschutzbeauftragter", first)
        self.assertNotIn("Lagerhelfer", first)
        self.assertNotIn("Chef", first)  # ring 2 (Berlin) is not asked for
        self.assertIn("student-job", first)
        self.assertIn("visa-sponsorship", first)  # it also appears in the visa feed
        self.assertIn("english", first)
        self.assertNotIn("wakeAgent", first)
        ba_call = next(h for u, h in net.calls if "arbeitsagentur" in u)
        self.assertEqual(ba_call["X-API-Key"], "jobboerse-jobsuche")

        index = json.loads((self.tmp / "data" / "jobs_index.json").read_text())
        self.assertTrue(all(key.startswith("J-") for key in index))

        second = job_scan.run({0, 1}, dry_run=False)
        self.assertIn("(none)", second)
        self.assertTrue(second.rstrip().endswith('{"wakeAgent": false}'))

    def test_dry_run_keeps_state_untouched(self):
        self.use_net(FakeNet(self.routes()))
        job_scan.run({0, 1}, dry_run=True)
        self.assertFalse((self.tmp / "state" / "seen_jobs.json").exists())

    def test_all_sources_down_still_wakes_agent(self):
        self.use_net(FakeNet(self.routes(), fail=("arbeitsagentur", "arbeitnow")))
        out = job_scan.run({0, 1}, dry_run=False)
        self.assertIn("✗ Bundesagentur", out)
        self.assertNotIn("wakeAgent", out)

    def test_feedback_roundtrip(self):
        self.use_net(FakeNet(self.routes()))
        job_scan.run({0, 1}, dry_run=False)
        job_id = next(iter(json.loads((self.tmp / "data" / "jobs_index.json").read_text())))
        sys.argv = ["glctl.py", "job", "rate", job_id.lower(), "down", "needs", "German"]
        with contextlib.redirect_stdout(io.StringIO()):
            glctl.main()
        self.assertIn("needs German", "\n".join(job_scan.recent_feedback()))


class MorningBriefTests(ProjectCase):
    def test_brief_sections(self):
        net = FakeNet({"open-meteo": WEATHER, "canteens?": CANTEENS, "/meals": MEALS,
                       "news.google.com": RSS, "16vor": ATOM, "dw.com": RDF},
                      fail=("volksfreund",))
        self.use_net(net)
        sys.argv = ["morning_brief.py"]
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            morning_brief.main()
        out = buffer.getvalue()
        self.assertIn("today: light rain, 7–14 °C, rain chance 70%", out)
        self.assertIn("Trier, Mensa Tarforst:", out)
        self.assertNotIn("Luxembourg Campus", out)
        self.assertIn("Gemüsecurry (Vegan) — €2.90 students", out)
        self.assertIn("Neue Mensa in Trier eröffnet", out)
        self.assertNotIn("Old story", out)
        self.assertIn("✗ Trierischer Volksfreund", out)
        self.assertEqual(out.count("Neue Mensa in Trier eröffnet"), 1)  # same story, many feeds

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            morning_brief.main()
        self.assertNotIn("Neue Mensa in Trier eröffnet", buffer.getvalue())  # shown yesterday


class DataToolTests(ProjectCase):
    def ctl(self, *args):
        sys.argv = ["glctl.py", *args]
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            glctl.main()
        return buffer.getvalue()

    def test_workdays_count_full_half_and_hiwi(self):
        year = TODAY.year
        self.ctl("work", "add", "--hours", "5", "--employer", "A", "--date", f"{year}-01-05")
        self.ctl("work", "add", "--hours", "3", "--employer", "A", "--date", f"{year}-01-06")
        self.ctl("work", "add", "--hours", "2", "--employer", "B", "--date", f"{year}-01-06")  # same day: 5 h
        self.ctl("work", "add", "--hours", "4", "--employer", "A", "--date", f"{year}-01-07")
        self.ctl("work", "add", "--hours", "6", "--employer", "Uni", "--date", f"{year}-01-08", "--kind", "hiwi")
        summary = gl.workdays_summary(year)
        self.assertEqual((summary["full"], summary["half"], summary["used"], summary["hiwi_days"]), (2, 1, 2.5, 1))

    def test_deadline_add_and_reminders(self):
        due = TODAY + dt.timedelta(days=7)
        self.ctl("deadline", "add", "--date", due.isoformat(), "--title", 'Pay "fee"', "--category", "uni")
        self.assertIn('Pay "fee"', self.ctl("deadline", "list"))
        lines = deadlines.deadline_lines(TODAY, show_all=False)
        self.assertEqual(len(lines), 1)  # the templates' examples are ignored
        self.assertIn("in 7 days", lines[0])
        self.assertEqual(deadlines.deadline_lines(TODAY + dt.timedelta(days=1), show_all=False), [])

    def test_workday_alert_fires_once_per_threshold(self):
        start = dt.date(TODAY.year, 1, 1)
        with (self.tmp / "data" / "worklog.csv").open("w") as handle:
            handle.write("date,hours,employer,kind,note\n")
            for i in range(101):
                handle.write(f"{start + dt.timedelta(days=i)},8,A,regular,\n")
        self.assertTrue(deadlines.workday_lines(TODAY, dry_run=False))
        self.assertEqual(deadlines.workday_lines(TODAY, dry_run=False), [])


if __name__ == "__main__":
    unittest.main()
