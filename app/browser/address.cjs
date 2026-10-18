// Pure helpers for Atlas's in-app browser; kept free of Electron so tests can load them.

function isWeb(url) {
  try { return ['https:', 'http:'].includes(new URL(url).protocol); } catch { return false; }
}

// Turns what someone typed in the address field into a web URL, or null.
function addressURL(text) {
  const value = String(text || '').trim();
  if (!value || /\s/.test(value)) return null;
  if (isWeb(value)) return new URL(value).href;
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(value)) return null;
  try {
    const url = new URL(`https://${value}`);
    if (url.username || url.password) return null;
    return url.hostname.includes('.') || url.hostname === 'localhost' ? url.href : null;
  } catch { return null; }
}

// Sites treat Electron's user agent as an unknown browser; present the Chrome it is built on.
function chromeUserAgent(agent) {
  return String(agent || '').replace(/ \(\+https?:[^)]*\)/g, '').replace(/ (Electron|Atlas|atlas-local)\/\S+/g, '');
}

// Page translation goes through Google Translate's website proxy: www.trier.de becomes
// www-trier-de.translate.goog, which serves the page translated and keeps its links translated.
const PROXY = '.translate.goog';

function isTranslated(url) {
  try { return new URL(url).hostname.endsWith(PROXY); } catch { return false; }
}

function translatedURL(url, language = 'en') {
  if (!isWeb(url) || isTranslated(url)) return url;
  const original = new URL(url);
  const proxied = new URL(original.href);
  proxied.protocol = 'https:';
  proxied.port = '';
  proxied.hostname = original.hostname.replaceAll('-', '--').replaceAll('.', '-') + PROXY;
  proxied.searchParams.set('_x_tr_sl', 'auto');
  proxied.searchParams.set('_x_tr_tl', language);
  proxied.searchParams.set('_x_tr_hl', language);
  if (original.protocol === 'http:') proxied.searchParams.set('_x_tr_sch', 'http');
  return proxied.href;
}

function originalURL(url) {
  if (!isTranslated(url)) return url;
  const proxied = new URL(url);
  const original = new URL(proxied.href);
  const host = proxied.hostname.slice(0, -PROXY.length);
  original.hostname = host.replaceAll('--', '\0').replaceAll('-', '.').replaceAll('\0', '-');
  original.protocol = proxied.searchParams.get('_x_tr_sch') === 'http' ? 'http:' : 'https:';
  for (const key of [...original.searchParams.keys()]) if (key.startsWith('_x_tr_')) original.searchParams.delete(key);
  return original.href;
}

module.exports = { isWeb, addressURL, chromeUserAgent, isTranslated, translatedURL, originalURL };
