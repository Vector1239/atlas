const $ = id => document.getElementById(id);
const address = $('address');
let state = { active: null, tabs: [], page: null };

function shown(url) {
  try { const parsed = new URL(url); return parsed.protocol === 'https:' ? parsed.href.slice(8) : parsed.href; } catch { return url || ''; }
}

function tabButton(id, title, { loading = false, closable = true } = {}) {
  const tab = document.createElement('div');
  tab.className = 'tab' + (state.active === id ? ' selected' : '') + (loading ? ' loading' : '');
  tab.setAttribute('role', 'tab');
  tab.setAttribute('aria-selected', String(state.active === id));
  const label = document.createElement('button');
  label.className = 'tab-label';
  label.title = title;
  label.onclick = () => window.atlasBrowser.command('select', id === null ? 'atlas' : String(id));
  label.onauxclick = event => { if (event.button === 1 && closable) window.atlasBrowser.command('close', String(id)); };
  const mark = document.createElement('span');
  mark.className = id === null ? 'mark atlas' : 'mark';
  if (id === null) mark.textContent = 'A';
  const text = document.createElement('span');
  text.className = 'tab-title';
  text.textContent = title;
  label.append(mark, text);
  tab.append(label);
  if (closable) {
    const close = document.createElement('button');
    close.className = 'tab-close';
    close.title = 'Close tab (⌘W)';
    close.setAttribute('aria-label', `Close ${title}`);
    close.innerHTML = '<svg viewBox="0 0 256 256"><path d="M200 56 56 200M200 200 56 56"/></svg>';
    close.onclick = () => window.atlasBrowser.command('close', String(id));
    tab.append(close);
  }
  return tab;
}

function render() {
  const strip = $('strip');
  strip.replaceChildren(tabButton(null, 'Atlas', { closable: false }),
    ...state.tabs.map(tab => tabButton(tab.id, tab.title || 'Loading…', { loading: tab.loading })));
  const page = state.page;
  $('toolbar').hidden = !page;
  if (!page) return;
  $('back').disabled = !page.back;
  $('forward').disabled = !page.forward;
  $('reload').classList.toggle('loading', page.loading);
  $('reload').title = page.loading ? 'Stop loading' : 'Reload (⌘R)';
  $('progress').classList.toggle('active', page.loading);
  $('lock').classList.toggle('insecure', page.url.startsWith('http:'));
  $('external').disabled = !page.url;
  if (document.activeElement !== address) address.value = shown(page.url);
  const translation = page.translation || {};
  const foreign = page.language && !/^en\b/i.test(page.language);
  $('translate').classList.toggle('on', Boolean(translation.on));
  $('translate').classList.toggle('suggested', Boolean(foreign) && !translation.on);
  $('translate-label').textContent = translation.on ? 'Show original' : 'Translate';
  $('translate').title = translation.on ? 'Show the page in its original language' : 'Translate this page to English on this Mac. Right-click for options.';
  $('translate').disabled = !page.url;
  const note = page.failure || translation.failure || (!translation.on ? ''
    : translation.downloading ? 'Downloading the translation model (one time only)…'
    : translation.busy ? 'Translating on this Mac…'
    : `Translated${translation.from ? ` from ${translation.from}` : ''} on this Mac`);
  $('note').textContent = document.activeElement === address ? '' : note;
  $('note').classList.toggle('failure', Boolean(page.failure || translation.failure));
}

window.atlasBrowser.onState(next => { state = next; render(); });
window.atlasBrowser.onFocusAddress(() => { address.focus(); address.select(); });

$('back').onclick = () => window.atlasBrowser.command('back');
$('forward').onclick = () => window.atlasBrowser.command('forward');
$('reload').onclick = () => window.atlasBrowser.command(state.page && state.page.loading ? 'stop' : 'reload');
$('translate').onclick = () => window.atlasBrowser.command('translate');
$('translate').oncontextmenu = event => { event.preventDefault(); window.atlasBrowser.command('translate-options'); };
$('external').onclick = () => window.atlasBrowser.command('external');
$('address-form').onsubmit = event => { event.preventDefault(); window.atlasBrowser.command('go', address.value); address.blur(); };
address.onfocus = () => { if (state.page) address.value = state.page.url; address.select(); render(); };
address.onblur = render;
address.onkeydown = event => { if (event.key === 'Escape') { address.value = state.page ? state.page.url : ''; address.blur(); } };
