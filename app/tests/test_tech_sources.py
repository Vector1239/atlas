import datetime as dt
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tech_sources as sources

TODAY = dt.date(2026,10,17)


class TechSourceTests(unittest.TestCase):
    def test_ical_unfolds_text_unescapes_and_honours_exclusive_end_dates(self):
        calendar = 'BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nSUMMARY:Long\\, event\r\n  name\r\nDTSTART;VALUE=DATE:20261227\r\nDTEND;VALUE=DATE:20261231\r\nURL:https://event.example/\r\nLOCATION:Hamburg\\, Germany\r\nEND:VEVENT\r\nEND:VCALENDAR'
        row = sources.ical_rows(calendar,'Calendar','https://calendar.example/',TODAY)[0]
        self.assertEqual(row['title'],'Long, event name')
        self.assertEqual(row['end'],'2026-12-30')
        self.assertEqual(row['venue'],'Hamburg, Germany')

    def test_ical_keeps_timezone_and_cancellations_but_does_not_guess_recurrences(self):
        event = 'BEGIN:VEVENT\nSUMMARY:Meetup\nDTSTART;TZID=Europe/Berlin:20261027T200000\nDTEND;TZID=Europe/Berlin:20261027T220000\nSTATUS:CANCELLED\nURL:https://event.example/\nEND:VEVENT\n'
        rows = sources.ical_rows('BEGIN:VCALENDAR\n'+event+'END:VCALENDAR','Calendar','https://calendar.example/',TODAY)
        self.assertTrue(rows[0]['cancelled'])
        self.assertEqual(rows[0]['starts_at'],'2026-10-27T20:00:00+01:00')
        self.assertIn('CET',rows[0]['time_note'])
        self.assertEqual(sources.ical_rows(('BEGIN:VCALENDAR\n'+event+'END:VCALENDAR').replace('STATUS:CANCELLED','RRULE:FREQ=WEEKLY'),'Calendar','https://calendar.example/',TODAY),[])
        with self.assertRaises(ValueError):
            sources.ical_rows('<html>Login required</html>','Calendar','https://calendar.example/',TODAY)

    def test_labelled_venue_is_available_when_calendar_omits_location(self):
        text = 'BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:AI Breakfast\nDTSTART:20261022T083000\nDESCRIPTION:Practical info\\nPlace: Chamber of Commerce, Luxembourg. Please note a different venue for July.\\nTime: 08:30\nURL:https://event.example/\nEND:VEVENT\nEND:VCALENDAR'
        self.assertEqual(sources.ical_rows(text,'Calendar','https://calendar.example/',TODAY)[0]['venue'],'Chamber of Commerce, Luxembourg.')

    def test_expanded_local_meetups_keep_occurrences_and_daylight_saving(self):
        events = [{'summary':'Chaostreff','uid':'same-series','dtstart':'2026-10-20T18:00:00+00:00','dtend':'2026-10-20T21:59:00+00:00'},
                  {'summary':'Chaostreff','uid':'same-series','dtstart':'2026-10-27T19:00:00+00:00','dtend':'2026-10-27T22:59:00+00:00'}]
        rows = sources.maschinendeck_rows({'code':200,'data':events},TODAY)
        self.assertEqual(len(rows),2)
        self.assertNotEqual(rows[0]['id'],rows[1]['id'])
        self.assertEqual([row['series_id'] for row in rows],['same-series','same-series'])
        self.assertEqual(rows[0]['time_note'],'20:00–23:59 CEST')
        self.assertEqual(rows[1]['time_note'],'20:00–23:59 CET')
        self.assertTrue(all(row['city']=='Trier' for row in rows))

    def test_maschinendeck_calendar_export_shows_expanded_meetings_in_trier_time(self):
        def instance(day, hour):
            return f'BEGIN:VEVENT\nUID:chaostreff\nRECURRENCE-ID:202610{day}T{hour}0000Z\nSUMMARY:Chaostreff\nDTSTART:202610{day}T{hour}0000Z\nDTEND:202610{day}T{hour}5900Z\nEND:VEVENT\n'
        calendar = 'BEGIN:VCALENDAR\n' + instance(20,18) + instance(27,19) + 'END:VCALENDAR'
        rows = sources.maschinendeck_calendar_rows(calendar,TODAY)
        self.assertEqual([row['time_note'] for row in rows],['20:00–20:59 CEST','20:00–20:59 CET'])
        self.assertEqual([row['series_id'] for row in rows],['chaostreff','chaostreff'])
        self.assertTrue(all(row['city']=='Trier' and row['url']=='https://maschinendeck.org/' and row['description'] for row in rows))
        late = calendar.replace('20261027T190000Z','20261027T233000Z').replace('20261027T195900Z','20261027T235900Z')
        self.assertEqual(sources.maschinendeck_calendar_rows(late,TODAY)[1]['start'],'2026-10-28')

    def test_maschinendeck_api_also_accepts_a_bare_event_list(self):
        event = {'summary':'Chaostreff','uid':'s','dtstart':'2026-10-20T18:00:00+00:00','dtend':'2026-10-20T21:59:00+00:00'}
        self.assertEqual(len(sources.maschinendeck_rows([event,'junk'],TODAY)),1)
        with self.assertRaises(ValueError):
            sources.maschinendeck_rows({'code':503,'data':None},TODAY)

    def test_calendar_without_event_url_can_link_to_the_page_named_in_its_description(self):
        text = 'BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:PyCon DE\nDTSTART;VALUE=DATE:20270414\nDTEND;VALUE=DATE:20270417\nLOCATION:Darmstadt\\, Germany\nDESCRIPTION:<a href="https://2027.pycon.de/">PyCon DE</a>\nEND:VEVENT\nEND:VCALENDAR'
        self.assertEqual(sources.ical_rows(text,'Python','https://www.python.org/events/',TODAY,link_in_description=True)[0]['url'],'https://2027.pycon.de/')
        self.assertEqual(sources.ical_rows(text,'Python','https://www.python.org/events/',TODAY)[0]['url'],'https://www.python.org/events/')

    def test_mlh_reads_published_microdata_not_location_name_as_event_title(self):
        markup = '''<a itemScope itemType="https://schema.org/Event" href="https://hack.example/?tracking=1"><meta itemProp="url" content="https://hack.example/"><meta itemProp="startDate" content="2026-11-13T12:00:00Z"><meta itemProp="endDate" content="2026-11-15T18:00:00Z"><meta itemProp="isAccessibleForFree" content="true"><div itemProp="location"><span itemProp="name">London</span><meta itemProp="addressLocality" content="London"><meta itemProp="addressCountry" content="GB"></div><h4>University Hackathon</h4></a>'''
        row = sources.mlh_rows(markup,'https://www.mlh.com/seasons/2027/events',TODAY)[0]
        self.assertEqual(row['title'],'University Hackathon')
        self.assertEqual(row['country'],'United Kingdom')
        self.assertEqual(row['url'],'https://hack.example/')
        self.assertIn('Free',row['cost'])
        with self.assertRaises(ValueError):
            sources.mlh_rows('<html>Service unavailable</html>','https://www.mlh.com/',TODAY)

    def test_devpost_submission_windows_handle_same_month_and_year_rollover(self):
        self.assertEqual(sources.submission_dates('Oct 05 - 27, 2026'),('2026-10-05','2026-10-27'))
        self.assertEqual(sources.submission_dates('Dec 20 - Jan 10, 2027'),('2026-12-20','2027-01-10'))
        self.assertEqual(sources.submission_dates('Dec 20, 2026 - Jan 10, 2027'),('2026-12-20','2027-01-10'))
        with self.assertRaises(ValueError):
            sources.submission_dates('Dates to be announced')

    def test_devpost_labels_submission_dates_and_preserves_prize_topics_and_rules(self):
        event = {'title':'Build something','url':'https://build.devpost.com/','submission_period_dates':'Oct 01 - Nov 12, 2026','open_state':'open','displayed_location':{'location':'Online'},'prize_amount':'$<span>10,000</span>','invite_only':True,'themes':[{'name':'Machine Learning/AI'}]}
        rows = sources.devpost_rows({'hackathons':[event,{**event,'open_state':'closed'}]},TODAY)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['date_note'],'Submission window')
        self.assertEqual(rows[0]['prize'],'$ 10,000')
        self.assertEqual(rows[0]['eligibility'],'Invitation required')
        self.assertEqual(rows[0]['topics'],['Machine Learning/AI'])

    def test_structured_event_details_are_plain_text_and_cancellation_is_retained(self):
        page = '''<script type="application/ld+json">{"@graph":[{"@type":"Event","name":"AI &amp; Security","startDate":"2026-10-22T08:30:00+02:00","endDate":"2026-10-22T11:00:00+02:00","url":"https://event.example/","description":"&lt;p&gt;A workshop.&lt;/p&gt;","location":{"name":"Workshop room","address":{"addressLocality":"Luxembourg","addressCountry":"LU"}},"organizer":{"name":"University"},"eventStatus":"https://schema.org/EventCancelled"}]}</script>'''
        row = sources.structured_rows(page,'Calendar','https://calendar.example/',TODAY)[0]
        self.assertEqual(row['title'],'AI & Security')
        self.assertEqual(row['description'],'A workshop.')
        self.assertEqual(row['country'],'Luxembourg')
        self.assertTrue(row['cancelled'])

    def test_visible_calendar_ticket_price_is_read_independently_of_json_currency(self):
        page = '<article class="tribe-events-calendar-list__event"><a href="https://event.example/">Event</a><span class="tribe-events-c-small-cta__price">€15 – €20</span></article>'
        self.assertEqual(sources.visible_prices(page),{'https://event.example/':'€15 – €20'})

    def test_links_with_credentials_and_script_schemes_are_never_event_destinations(self):
        for url in ['javascript:alert(1)','https://user:password@example.com/','file:///tmp/private']:
            self.assertFalse(sources.valid_url(url))
