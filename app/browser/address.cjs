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

module.exports = { isWeb, addressURL, chromeUserAgent };
