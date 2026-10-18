import datetime as dt
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[2] / 'germany-life-hermes/scripts')]
import discovery


class DiscoveryTests(unittest.TestCase):
    def test_new_job_cities_get_pins_only_for_exact_matches_in_the_listed_region(self):
        towns = [{'name': 'Kirchberg', 'country_code': 'DE', 'feature_code': 'PPL', 'latitude': 50.6, 'longitude': 12.5, 'admin1': 'Saxony', 'population': 9000},
                 {'name': 'Kirchberg', 'country_code': 'DE', 'feature_code': 'PPL', 'latitude': 49.9, 'longitude': 7.4, 'admin1': 'Rhineland-Palatinate', 'population': 3800},
                 {'name': 'Hamburg', 'country_code': 'DE', 'feature_code': 'PPLA', 'latitude': 53.55, 'longitude': 10.0, 'population': 1800000}]
        fetch = lambda url: {'results': [row for row in towns if row['name'].startswith(url.split('name=')[1].split('&')[0])]}
        with tempfile.TemporaryDirectory() as folder, patch.dict(discovery.GEOCODED, clear=True):
            path = Path(folder) / 'places.json'
            discovery.geocode([('Kirchberg, Jagst', 'DE', 'Rhineland-Palatinate'), ('Hamb', 'DE', ''), ('Remote', 'DE', '')], path, fetch)
            self.assertEqual(discovery.city_location('Kirchberg, Jagst')['lon'], 7.4)
            self.assertIsNone(discovery.city_location('Hamb'))
            self.assertIsNone(discovery.city_location('Remote'))
            self.assertEqual(discovery.geocode([('Hamb', 'DE', '')], path, fetch), 0)  # cached, not asked again

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

    def test_jsearch_city_pins_follow_provider_country_and_keep_unknown_distance(self):
        job = {'title': 'Data Scientist', 'where': 'Eindhoven', 'city': 'Eindhoven', 'source': 'JSearch', 'country': 'NL'}
        row = discovery.enrich_job(job)
        self.assertIsNotNone(row['location'])
        self.assertIsNone(row['distance_from_trier'])
        self.assertIsNone(discovery.enrich_job({**job, 'country': 'DE'})['location'])

    def test_headline_translation_survives_known_publisher_suffix_without_merging_different_stories(self):
        title = 'Trier, Eifel, Mosel: Die Events-Tipps fürs Wochenende – Von Dinosauriern bis zu Musik-Highlights'
        original = title + ' - Volksfreund'
        row = discovery.enrich_news({'title': original, 'source':'Volksfreund', 'lang':'de'})
        self.assertEqual(row['title'], original)
        self.assertFalse(row['translation_needed'])
        self.assertIn('Weekend event tips', row['title_en'])
        other = discovery.enrich_news({'title':'Neue Ausstellung - neue Preise', 'source':'The Paper', 'lang':'de'}, {'Neue Ausstellung - neues Museum':'New exhibition — new museum'})
        self.assertTrue(other['translation_needed'])

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

    def test_himalayas_timezone_labels_cover_saved_and_fresh_listings(self):
        offsets = list(range(-11,15)) + [-9.5,-3.5,3.5,4.5,5.5,5.75,6.5,8.75,9.5,10.5,12.75]
        job = {'title':'Backend Engineer','source':'Himalayas','remote':True,'city':'Remote',
               'remote_scope':'Worldwide', 'region_name':'Worldwide · Timezones: ' + ', '.join(map(str,offsets))}
        old = discovery.enrich_job(job)
        self.assertEqual(old['region_name'],'Worldwide')
        self.assertEqual(old['timezone_label'],'Germany time supported')
        self.assertIsNone(old['location'])
        fresh = discovery.enrich_job({**job,'remote_timezones':['UTC+1','UTC+5:30']})
        self.assertEqual(fresh['timezone_label'],'Germany time supported')
        self.assertIn('4 hours 30 minutes ahead of Germany', fresh['timezone_details'])
        germany = discovery.enrich_job({**job,'remote_scope':'Germany','remote_timezones':[1]})
        self.assertEqual(germany['region_name'],'Germany')
        self.assertEqual(germany['timezone_label'],'Germany time supported')
        restricted = discovery.timezone_summary([-8,-7,-6,-5])
        self.assertEqual(restricted[0],'Different from Germany time · see details')
        self.assertIn('9 hours behind Germany (winter)',restricted[1])
        self.assertEqual(discovery.timezone_summary([])[0],'Germany time supported')

    def test_german_level_is_added_to_saved_jobs_and_preferences_are_separate(self):
        base = {'title':'Engineer','source':'Himalayas','city':'Remote','flags':[]}
        result = discovery.enrich_job({**base,'text':'German B1 required, English C1 preferred.'})
        self.assertEqual(result['german_requirement']['label'],'German B1 required')
        self.assertIn('german-required',result['flags'])
        abbreviation = discovery.enrich_job({**base,'text':'Deutsch-Kenntnisse (mind. B1 Level) bringst du mit.'})
        self.assertEqual(abbreviation['german_requirement']['label'],'German B1 required')
        preferred = discovery.enrich_job({**base,'flags':['german-required'],'text':'German B2 is a nice-to-have.'})
        self.assertEqual(preferred['german_requirement']['status'],'preferred')
        self.assertNotIn('german-required',preferred['flags'])

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
