import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const { isWeb, addressURL, chromeUserAgent } = createRequire(import.meta.url)('../browser/address.cjs');

test('only http and https links count as web links', () => {
  assert.equal(isWeb('https://www.ticketmaster.de/event/123'), true);
  assert.equal(isWeb('http://www.trier.de/'), true);
  for (const url of ['mailto:a@b.de', 'file:///etc/passwd', 'javascript:alert(1)', 'not a url', '']) assert.equal(isWeb(url), false, url);
});

test('typed addresses become https URLs and everything else is refused', () => {
  assert.equal(addressURL('trier.de'), 'https://trier.de/');
  assert.equal(addressURL('  www.ticketmaster.de/discover  '), 'https://www.ticketmaster.de/discover');
  assert.equal(addressURL('http://example.com/a?b=1'), 'http://example.com/a?b=1');
  assert.equal(addressURL('localhost:4173'), 'https://localhost:4173/');
  for (const text of ['', 'concerts in trier', 'trier', 'file:///etc/passwd', 'javascript:alert(1)', 'mailto:a@b.de', 'ftp://example.com']) {
    assert.equal(addressURL(text), null, text);
  }
});

test('the browser presents a plain Chrome user agent', () => {
  const electron = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Atlas/1.12.12 Chrome/152.0.7977.167 Electron/44.9.0 Safari/537.36 Atlas/1.12.12 (+https://github.com/Vector1239/atlas)';
  assert.equal(chromeUserAgent(electron), 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.7977.167 Safari/537.36');
});
