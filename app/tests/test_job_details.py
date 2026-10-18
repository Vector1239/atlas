import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[2] / "germany-life-hermes/scripts")]
import job_details


class JobDetailTests(unittest.TestCase):
    def test_structured_posting_in_graph_or_list_wins_over_page_noise(self):
        description = "We need a working student with Python, SQL and data analysis experience. " * 3
        for payload in ({"@graph": [{"@type": "WebPage"}, {"@type": ["Thing", "JobPosting"], "description": "<p>" + description + "</p>"}]},
                        [{"@type": "JobPosting", "description": description}]):
            text, source = job_details.posting_text('<body><nav>Navigation</nav><script type="application/ld+json">' + json.dumps(payload) + '</script></body>')
            self.assertIn("Python", text)
            self.assertNotIn("Navigation", text)
            self.assertEqual(source, "JobPosting structured data")

    def test_main_text_fallback_ignores_scripts_navigation_and_footer(self):
        text, source = job_details.posting_text('<body><nav>Navigation</nav><div role="main">' + 'Required experience in Python and SQL. ' * 5 + '<script>tracking()</script></div><footer>Cookie footer</footer></body>')
        self.assertIn("Python", text)
        self.assertNotIn("Cookie", text)
        self.assertNotIn("tracking", text)
        self.assertEqual(source, "Listing page")
        self.assertEqual(job_details.posting_text('<main>Loading…</main>'), ("", ""))

    def test_bundesagentur_detail_cached_and_failed_api_falls_back_to_public_page(self):
        job = {"source": "Bundesagentur", "source_id": "10000-test-S", "url": "https://www.arbeitsagentur.de/jobsuche/jobdetail/10000-test-S"}
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(job_details.job_providers, "bundesagentur_description", return_value="Full job requirements") as request, patch.object(job_details.news_media, "fetch_public") as page:
                first = job_details.load(job, Path(folder))
                self.assertEqual(job_details.load(job, Path(folder)), first)
                self.assertEqual(request.call_count, 1)
                page.assert_not_called()
        with tempfile.TemporaryDirectory() as folder:
            body = ('<main>' + 'Student role requiring Python and SQL. ' * 5 + '</main>').encode()
            with patch.object(job_details.job_providers, "bundesagentur_description", side_effect=ValueError("unavailable")), patch.object(job_details.news_media, "fetch_public", return_value=(body, 'text/html', job['url'])):
                self.assertIn("Python", job_details.load(job, Path(folder))["text"])

    def test_failure_is_cached_without_inventing_requirements(self):
        job = {"source": "Bundesagentur", "source_id": "missing", "url": "https://www.arbeitsagentur.de/jobsuche/jobdetail/missing"}
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(job_details.job_providers, "bundesagentur_description", side_effect=ValueError("unavailable")) as request, patch.object(job_details.news_media, "fetch_public", side_effect=ValueError("blocked")):
                result = job_details.load(job, Path(folder))
                self.assertEqual(result["text"], "")
                self.assertIn("original listing", result["detail_error"])
                job_details.load(job, Path(folder))
                self.assertEqual(request.call_count, 1)
