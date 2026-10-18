"""German requirements must keep language, CEFR level and optionality together."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'scripts'))
from job_language import german_requirement
from job_scan import Matcher


class GermanLanguageTests(unittest.TestCase):
    def test_cefr_levels_both_orders_and_both_languages(self):
        for level in ['A1','A2','B1','B2','C1','C2']:
            self.assertEqual(german_requirement(f'German {level} required')["level"],level)
        for text, level in [
            ('German B1 required','B1'),
            ('German language skills at least at B2 level are required.','B2'),
            ('Deutschkenntnisse mindestens B1 erforderlich.','B1'),
            ('Du sprichst Deutsch auf dem Niveau C1.','C1'),
            ('B2 level German is required.','B2'),
            ('C1 in German required.','C1'),
            ('German (B1/B2) is required.','B1–B2'),
            ('Deutsch B1–2 erforderlich','B1–B2'),
            ('German A2+ required.','A2+'),
            ('Du bringst auch Deutsch-Kenntnisse (mind. B1 Level) mit.','B1'),
            ('Sehr gute Deutschkenntnisse sind Voraussetzung (mind. Level C1), gute Englischkenntnisse runden dein Profil ab.','C1'),
            ('German skills min. B1 required.','B1'),
            ('B1-Level German required.','B1'),
            ('<li>German <strong>B1</strong> required</li>','B1')]:
            with self.subTest(text=text):
                row = german_requirement(text)
                self.assertEqual(row['level'],level)
                self.assertEqual(row['status'],'required')
                self.assertTrue(row['evidence'])
                self.assertIn('german-required',Matcher({}).flags({'title':'Engineer','text':text}))

    def test_english_cefr_and_german_qualitative_cannot_be_confused(self):
        self.assertEqual(german_requirement('English C1 required; fluent German required.')['level'],None)
        self.assertEqual(german_requirement('German fluency and English C1 required.')['level'],None)
        self.assertEqual(german_requirement('German B1 required, English C1 preferred.')['label'],'German B1 required')
        self.assertEqual(german_requirement('English C1 required and German B1 preferred.')['label'],'German B1 preferred')
        self.assertEqual(german_requirement('German B1 required and English not required.')['label'],'German B1 required')
        self.assertEqual(german_requirement('German B1 or French B2 required.')['status'],'mentioned')
        self.assertEqual(german_requirement('German B1 or higher and English C1 required.')['label'],'German B1 required')
        self.assertEqual(german_requirement('English B1 required. Version C2 of Python is used.')['status'],'unknown')

    def test_preferences_negations_and_training_are_not_required(self):
        for text,status in [('German B1 preferred.','preferred'),('German B2 is a nice-to-have.','preferred'),
                            ('Deutsch B2 wünschenswert.','preferred'),('German B1 is not required.','not_required'),
                            ('No German required. English C1 required.','not_required'),
                            ('We provide German B1 courses.','mentioned')]:
            with self.subTest(text=text):
                self.assertEqual(german_requirement(text)['status'],status)
                self.assertNotIn('german-required',Matcher({'german_required':['German']}).flags({'title':'Engineer','text':text}))
        row=german_requirement('German B1 required. German B2 preferred.')
        self.assertEqual(row['label'],'German B1 required')

    def test_fluent_is_not_assumed_to_be_a_cefr_level(self):
        for text in ['Fluent German required.','Verhandlungssichere Deutschkenntnisse.','German required.']:
            row=german_requirement(text)
            self.assertEqual(row['status'],'required')
            self.assertIsNone(row['level'])
