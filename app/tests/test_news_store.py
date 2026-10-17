import datetime as dt
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from news_store import merge_news


class NewsRetentionTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 10, 17, 20, tzinfo=dt.timezone.utc)
        self.story = {'title':'Weekend events in Trier', 'source':'Publisher', 'url':'https://publisher.example/story', 'published':'2026-10-17T15:36:00+02:00', 'ring':0}

    def test_story_stays_when_feed_rotates_and_expires_after_fourteen_days(self):
        retained = merge_news([self.story], [], self.now)
        self.assertEqual(retained[0]['url'], self.story['url'])
        self.assertEqual(merge_news(retained, [], self.now + dt.timedelta(days=15)), [])

    def test_refresh_updates_metadata_and_merges_publisher_suffix_duplicates(self):
        incoming = {**self.story, 'title':self.story['title'] + ' - Publisher', 'url':'https://news.google.com/rss/articles/1', 'image':'https://publisher.example/photo.jpg'}
        rows = merge_news([self.story], [incoming], self.now)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['image'], incoming['image'])
        self.assertEqual(rows[0]['article_url'], self.story['url'])
        self.assertEqual(len(merge_news(rows, [incoming], self.now)), 1)

    def test_same_story_with_changed_title_does_not_duplicate_its_url(self):
        self.assertEqual(len(merge_news([self.story], [{**self.story,'title':'Updated headline'}], self.now)), 1)

    def test_undated_story_ages_from_first_seen_instead_of_living_forever(self):
        rows = merge_news([], [{**self.story, 'published':None}], self.now)
        self.assertEqual(merge_news(rows, [], self.now + dt.timedelta(days=15)), [])
