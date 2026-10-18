"""Aggregation contracts across incomplete and mixed-provider listings."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import job_insights as insights


class MarketTests(unittest.TestCase):
    def test_all_sources_and_skill_fields_count_once_with_explicit_denominator(self):
        jobs = [
            {'id':'1','source':'Himalayas','title':'Backend Engineer (TypeScript)','tags':['Python','SQL'], 'skills':['SQL'], 'text':''},
            {'id':'2','source':'JSearch','title':'Engineer','skills':['Python'], 'text':'Python Python SQL'},
            {'id':'3','source':'Bundesagentur','title':'Engineer', 'text':''},
            {'id':'4','source':'Jobicy','title':'QA Analyst', 'text':'SQL'}]
        result = insights.analyze(jobs)
        self.assertEqual(result['total'],4)
        self.assertEqual(result['described'],2)
        self.assertEqual(result['skill_evidence'],3)
        counts = {r['name']:r for r in result['skills']}
        self.assertEqual((counts['SQL']['count'],counts['SQL']['share']),(3,.75))
        self.assertEqual((counts['Python']['count'],counts['Python']['share']),(2,.5))
        self.assertEqual(sum(r['count'] for r in result['sources']),4)
        self.assertEqual(sum(r['count'] for r in result['families']),4)
        self.assertEqual(sum(r['count'] for r in result['levels']),4)
        self.assertEqual(insights.family(jobs[0]),'Backend, cloud & DevOps')
        self.assertEqual(insights.family(jobs[3]),'Software engineering')

    def test_unknown_seniority_and_vague_experience_are_not_numeric_estimates(self):
        jobs = [
            {'title':'Engineer','text':'Several years of experience with Python.'},
            {'title':'Sr. Backend Engineer','text':''},
            {'title':'Engineer','seniority':['Entry-level'],'experience_months':0},
            {'title':'Engineer','seniority':['Senior']},
            {'title':'Engineer','job_types':['Intern']},
            {'title':'Engineer','text':'First practical experience is useful.'},
            {'title':'Engineer','text':'At least 5 years of experience.'}]
        result = insights.analyze(jobs)
        levels = {r['name']:r['count'] for r in result['levels']}
        self.assertEqual(levels,{'Student & intern':1,'Entry & junior':1,'Professional':1,'Senior & lead':2,'Not stated':2})
        self.assertEqual(result['experience']['known'],2)
        self.assertEqual(result['experience']['unknown'],5)
        self.assertEqual(result['experience']['unspecified_years'],1)
        self.assertEqual(result['experience']['median'],2.5)

    def test_currencies_periods_and_missing_currency_stay_separate(self):
        jobs = [
            {'title':'Engineer','salary':{'currency':'EUR','period':'MONTH','min':4000,'max':6000}},
            {'title':'Engineer','salary':{'currency':'USD','period':'YEAR','min':100000,'max':140000}},
            {'title':'Contractor','salary':{'currency':'EUR','period':'HOURLY','min':50,'max':70}},
            {'title':'Engineer','salary':{'period':'YEAR','min':80000}},
            {'title':'Engineer','salary':{'currency':'EUR','period':'YEAR','min':float('nan'),'max':0}}]
        result = insights.analyze(jobs)['pay']
        self.assertEqual(result['known'],3)
        self.assertEqual(result['eur'],2)
        self.assertEqual(result['hourly']['median'],60)
        self.assertEqual(result['annual']['median'],60000)
        self.assertEqual({r['name']:r['count'] for r in result['currencies']},{'EUR':2,'USD':1})
        self.assertEqual(result['examples'][1]['currency'],'USD')
        self.assertEqual(insights.pay({},'Salary: 5000 EUR per year'),None)

    def test_empty_dataset_does_not_invent_requirements(self):
        result = insights.analyze([])
        self.assertEqual(result['total'],0)
        self.assertEqual(result['skills'],[])
        self.assertEqual(result['experience']['median'],None)
        self.assertEqual(result['pay']['annual'],None)
