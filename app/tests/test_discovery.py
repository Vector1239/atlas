import datetime as dt
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import discovery


class DiscoveryTests(unittest.TestCase):
    def test_english_headline_keeps_original_and_new_german_headline_waits(self):
        title = 'Uni Trier startet ins neue Semester: Mehr als 2.200 neue Studierende auf dem Campus - lokalo.de'
        item = {'title': title, 'lang': 'de'}
        row = discovery.enrich_news(item)
        self.assertIn('2,200', row['title_en'])
        self.assertEqual(row['title'], title)
        self.assertTrue(row['translated'])
        self.assertNotIn('title_en', item)
        # Article language wins over inaccurate feed metadata.
        english = discovery.enrich_news({'title': 'Where are the Trier musicians?', 'lang': 'de'})
        self.assertFalse(english['translation_needed'])
        german = discovery.enrich_news({'title': 'Neue Ausstellung im Stadtmuseum eröffnet', 'lang': 'en'})
        self.assertTrue(german['translation_needed'])
        self.assertFalse(german['translated'])
        self.assertEqual(discovery.enrich_news(german, {german['title']: 'New exhibition opens at the city museum'})['title_en'], 'New exhibition opens at the city museum')

    def test_city_pins_are_verified_country_matched_and_approximate(self):
        self.assertEqual(discovery.city_location('Trier')['precision'], 'city')
        self.assertIsNone(discovery.city_location('Trier', 'France'))
        self.assertIsNone(discovery.city_location('Unverified village'))
        self.assertLess(discovery.city_location('Simmern, Hunsrück')['lat'], 50)
        self.assertIsNotNone(discovery.city_location('Eindhoven', 'Netherlands'))

    def test_legacy_location_becomes_numeric_filterable_distance(self):
        row = discovery.enrich_job({'title': 'Data Engineer', 'where': 'Trier, RHEINLAND_PFALZ (1,5 km)', 'source': 'Bundesagentur'})
        self.assertEqual(row['city'], 'Trier')
        self.assertEqual(row['region_name'], 'Rhineland-Palatinate')
        self.assertEqual(row['distance_from_trier'], 1.5)

    def test_unknown_distance_is_not_zero_or_distance_from_another_city(self):
        job = {'title': 'Engineer', 'where': 'Berlin', 'source': 'Arbeitnow'}
        self.assertIsNone(discovery.enrich_job(job)['distance_from_trier'])
        job.update(distance_km=5, distance_origin='Berlin')
        self.assertIsNone(discovery.enrich_job(job)['distance_from_trier'])
        job.update(distance_km='NaN', distance_origin='Trier')
        self.assertIsNone(discovery.enrich_job(job)['distance_from_trier'])

    def test_translation_preserves_original_and_does_not_claim_english_eligibility(self):
        job = {'title': 'Werkstudierende (w/m/d) Reporting & Business Intelligence, Trier', 'flags': [], 'where': 'Trier'}
        row = discovery.enrich_job(job)
        self.assertIn('Working student', row['title_en'])
        self.assertEqual(row['title'], job['title'])
        self.assertIn('student-job', row['flags'])
        self.assertNotIn('english', row['flags'])
        self.assertEqual(job['flags'], [])

    def test_unseen_german_title_waits_for_actual_translation(self):
        job = {'title': 'Werkstudent für Nachhaltigkeitsforschung', 'where': 'Trier'}
        self.assertTrue(discovery.enrich_job(job)['translation_needed'])
        for title in ('Werkstudierende (w/m/d) Controlling', 'Softwareentwickler (m/w/d)', 'Datenanalyst (m/w/d) in Teilzeit'):
            self.assertTrue(discovery.enrich_job({'title': title})['translation_needed'], title)
        self.assertFalse(discovery.enrich_job({'title': 'Data Scientist (m/w/d)'})['translation_needed'])
        translated = discovery.enrich_job(job, {job['title']: 'Working student in sustainability research'})
        self.assertFalse(translated['translation_needed'])
        self.assertIn('sustainability', translated['title_en'])

    def test_ongoing_events_kept_expired_and_cancelled_removed(self):
        base = {'title': 'Test event', 'start': '2026-10-10', 'end': '2026-10-20', 'checked_at': '2026-10-01'}
        catalog = {'checked_at': '2026-10-01', 'calendars': [], 'events': [
            dict(base, id='ongoing'), dict(base, id='expired', end='2026-10-16'), dict(base, id='cancelled', cancelled=True)]}
        with patch.object(discovery, 'EVENT_CATALOG', catalog):
            rows = discovery.upcoming_events(dt.date(2026, 10, 17))['items']
        self.assertEqual([row['id'] for row in rows], ['ongoing'])
        self.assertTrue(rows[0]['ongoing'])
        self.assertTrue(rows[0]['stale'])


if __name__ == '__main__':
    unittest.main()
