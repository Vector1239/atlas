import hashlib
import json
from pathlib import Path
import socket
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import news_media as media


class NewsMediaTests(unittest.TestCase):
    def test_metadata_uses_article_image_and_alt_not_arbitrary_page_images(self):
        result = media.image_metadata('<img src="advert.jpg"><meta content="/story.jpg" property="og:image"><meta property="og:image:alt" content="A real caption &amp; credit">', 'https://publisher.example/story')
        self.assertEqual(result, {'url': 'https://publisher.example/story.jpg', 'alt': 'A real caption & credit'})
        self.assertIsNone(media.image_metadata('<meta property="og:image" content="/logo.png">', 'https://publisher.example/story'))
        self.assertIsNone(media.image_metadata('<img src="random.jpg">', 'https://publisher.example/story'))

    def test_private_addresses_credentials_and_non_https_are_never_preview_targets(self):
        for url in ('http://example.org/a.jpg', 'https://example.org:8443/a.jpg', 'https://name:secret@example.org/a.jpg', 'file:///etc/passwd'):
            with self.assertRaises(ValueError): media.public_target(url)
        for address in ('127.0.0.1', '192.168.1.1', '169.254.169.254', '::1', '10.0.0.1'):
            with patch.object(media.socket, 'getaddrinfo', return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', (address, 443))]):
                with self.assertRaises(ValueError): media.public_target('https://publisher.example/image')
        with patch.object(media.socket, 'getaddrinfo', return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('1.1.1.1', 443))]):
            self.assertEqual(media.public_target('https://publisher.example/image')[1], '1.1.1.1')

    def test_redirects_recheck_destination_and_size_and_content_type_are_bounded(self):
        class Response:
            status = 302
            def getheader(self, name, default=None): return 'https://127.0.0.1/private' if name == 'Location' else default
        class Connection:
            def __init__(self, *args): pass
            def request(self, *args, **kwargs): pass
            def getresponse(self): return Response()
            def close(self): pass
        with patch.object(media, 'PublicHTTPSConnection', Connection), patch.object(media, 'public_target', side_effect=[(media.urllib.parse.urlsplit('https://publisher.example/story'), '1.1.1.1'), ValueError('private')]) as target:
            with self.assertRaises(ValueError): media.fetch_public('https://publisher.example/story', 1000)
            self.assertEqual(target.call_args.args[0], 'https://127.0.0.1/private')
        Response.status = 200
        Response.getheader = lambda self, name, default=None: {'Content-Type': 'image/svg+xml', 'Content-Length': '100000'}.get(name, default)
        with patch.object(media, 'PublicHTTPSConnection', Connection), patch.object(media, 'public_target', return_value=(media.urllib.parse.urlsplit('https://publisher.example/image'), '1.1.1.1')):
            with self.assertRaises(ValueError): media.fetch_public('https://publisher.example/image', 1000, image=True)
            Response.getheader = lambda self, name, default=None: {'Content-Type':'image/jpeg', 'Content-Length':'100001'}.get(name, default)
            with self.assertRaisesRegex(ValueError, 'too large'): media.fetch_public('https://publisher.example/image', 1000, image=True)
            Response.getheader = lambda self, name, default=None: 'image/jpeg' if name == 'Content-Type' else default
            Response.read = lambda self, size: b'x' * size
            with self.assertRaisesRegex(ValueError, 'too large'): media.fetch_public('https://publisher.example/image', 1000, image=True)
        self.assertFalse(media.image_signature(b'<svg>' + b'x'*1000, 'image/png'))

    def test_actual_image_result_cached_by_content_and_reused_after_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            body = b'\xff\xd8\xff' + b'x' * 1024
            item = {'url':'https://publisher.example/story', 'title':'A story', 'source':'Publisher', 'image':'https://images.example/photo.jpg', 'image_alt':'A feed photo'}
            cache = media.NewsMedia(folder)
            with patch.object(media, 'fetch_public', return_value=(body, 'image/jpeg', item['image'])) as fetch:
                cache.start([item])
                deadline = time.monotonic() + 3
                while cache.status['running'] and time.monotonic() < deadline: time.sleep(.01)
                self.assertFalse(cache.status['running'])
                cache.start([item])
                self.assertEqual(fetch.call_count, 1)
            restarted = media.NewsMedia(folder)
            rows, _ = restarted.enrich([item])
            key = hashlib.sha256(body).hexdigest()
            self.assertEqual(rows[0]['picture']['url'], '/api/news/images/' + key)
            self.assertEqual(rows[0]['picture']['alt'], 'A feed photo')
            self.assertEqual(restarted.image(key), (body, 'image/jpeg'))
            self.assertIsNone(restarted.image('../atlas.json'))
            self.assertTrue(Path(folder, 'news_media.json').exists())

    def test_opaque_google_links_never_substitute_a_google_logo(self):
        self.assertIsNone(media.article_url({'url':'https://news.google.com/rss/articles/CBMiOpaqueLink'}))
        self.assertEqual(media.article_url({'url':'https://news.google.com/rss/articles/opaque', 'article_url':'https://publisher.example/article'}), 'https://publisher.example/article')


if __name__ == '__main__': unittest.main()
