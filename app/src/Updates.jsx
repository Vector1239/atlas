import React, { useEffect, useState } from 'react';
import { ArrowClockwiseIcon, ArrowDownIcon, ArrowUpRightIcon, CheckIcon, WarningCircleIcon } from '@phosphor-icons/react';

export default function Updates({ data, act }) {
  const [log, setLog] = useState(''), [logError, setLogError] = useState('');
  const update = data.updates || {};
  useEffect(() => {
    const query = new URLSearchParams(location.search);
    if (query.get('checkUpdates') === '1') {
      query.delete('checkUpdates');
      history.replaceState(null, '', `/?${query}`);
      act('/api/updates/check', {});
    }
  }, []);
  async function showLog() {
    try {
      const response = await fetch('/api/updates/log');
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Could not read the update log.');
      setLog(result.text); setLogError('');
    } catch (e) { setLogError(e.message); }
  }
  return <section className="card update-card" aria-label="Atlas updates">
    <div className="card-heading"><div><div className="eyebrow">KEEP ATLAS CURRENT</div><h2>App updates</h2></div><span className="badge sage">INSTALLED · v{data.version}</span></div>
    <p className="settings-description">Get the latest improvements from your Atlas repository. Atlas builds the update, installs it and restarts for you. Your profile, chats and personal data stay in place.</p>
    <div className="update-versions"><div><span>On this Mac</span><strong>Atlas {data.version}</strong>{update.installed_revision && <small>Build {update.installed_revision.slice(0, 7)}</small>}</div><div><span>GitHub · main</span><strong>{update.latest_version ? `Atlas ${update.latest_version}` : 'Not checked yet'}</strong>{update.latest_revision && <a href={`https://github.com/Vector1239/atlas/commit/${update.latest_revision}`} target="_blank" rel="noreferrer">View changes <ArrowUpRightIcon size={12} /></a>}</div></div>
    <div className={`update-status ${update.phase === 'error' ? 'failed' : ''}`} role="status">{update.running ? <span className="dot pulse" /> : update.phase === 'error' ? <WarningCircleIcon size={18} weight="bold" /> : ['current', 'complete'].includes(update.phase) ? <CheckIcon size={18} weight="bold" /> : <ArrowClockwiseIcon size={18} weight="bold" />}<div><strong>{update.message || 'Check for updates when you’re ready.'}</strong>{update.running && <small>{update.phase === 'checking' ? 'Looking for the latest changes on GitHub.' : 'Builds can take a few minutes. Atlas will restart after installation.'}</small>}</div></div>
    {update.blocked_reason && update.available && <p className="form-error">{update.blocked_reason}</p>}
    {(data.busy || data.translation?.running) && <p className="form-help">Finish the current request, or use Stop Gemma, before installing an update.</p>}
    {!update.supported && <p className="form-help">Open the installed Atlas Mac app to check for and install updates.</p>}
    <div className="update-actions"><button className="button secondary" disabled={!update.supported || update.running} onClick={() => act('/api/updates/check', {})}><ArrowClockwiseIcon size={16} weight="bold" />{update.phase === 'checking' ? 'Checking…' : 'Check for updates'}</button>{update.available && <button className="button" disabled={!update.supported || update.running || !update.can_install || data.busy || data.translation?.running} onClick={() => act('/api/updates/install', {})}><ArrowDownIcon size={16} weight="bold" />{update.running && update.phase !== 'checking' ? 'Updating…' : 'Update & restart'}</button>}<button className="text-button" onClick={showLog}>View update log</button></div>
    <p className="form-help update-checked">{update.checked_at && `Last checked ${new Date(update.checked_at).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })} · `}Updates come from <a href="https://github.com/Vector1239/atlas" target="_blank" rel="noreferrer">Vector1239/atlas</a>. Nothing is installed automatically.</p>
    {logError && <p className="form-error">{logError}</p>}{log && <pre className="log-output">{log}</pre>}
  </section>;
}
