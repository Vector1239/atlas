const $ = id => document.getElementById(id);
const address = $('address');
let current = { url: '', title: '', loading: false, back: false, forward: false, failure: '' };

function shown(url) {
  try { const parsed = new URL(url); return parsed.protocol === 'https:' ? parsed.href.slice(8) : parsed.href; } catch { return url || ''; }
}

function render() {
  $('back').disabled = !current.back;
  $('forward').disabled = !current.forward;
  $('reload').classList.toggle('loading', current.loading);
  $('reload').title = current.loading ? 'Stop loading' : 'Reload (⌘R)';
  $('progress').classList.toggle('active', current.loading);
  $('lock').classList.toggle('insecure', current.url.startsWith('http:'));
  $('external').disabled = !current.url;
  if (document.activeElement !== address) address.value = shown(current.url);
  $('title').textContent = document.activeElement === address ? '' : current.failure || current.title;
  $('title').classList.toggle('failure', Boolean(current.failure));
}

window.atlasBrowser.onState(state => { current = state; render(); });
window.atlasBrowser.onFocusAddress(() => { address.focus(); address.select(); });

$('back').onclick = () => window.atlasBrowser.command('back');
$('forward').onclick = () => window.atlasBrowser.command('forward');
$('reload').onclick = () => window.atlasBrowser.command(current.loading ? 'stop' : 'reload');
$('external').onclick = () => window.atlasBrowser.command('external');
$('address-form').onsubmit = event => { event.preventDefault(); window.atlasBrowser.command('go', address.value); address.blur(); };
address.onfocus = () => { address.value = current.url; address.select(); render(); };
address.onblur = render;
address.onkeydown = event => { if (event.key === 'Escape') { address.value = current.url; address.blur(); } };
