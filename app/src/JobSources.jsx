import React, { useState } from 'react';

export default function JobSources({ provider, refresh, act }) {
  const [host, setHost] = useState(provider?.host || 'openwebninja');
  const [key, setKey] = useState(''), [saving, setSaving] = useState(false);
  async function save(remove = false) {
    setSaving(true);
    try {
      const result = await act('/api/jobs/provider', { host, key: remove ? '' : key.trim() }, remove ? 'JSearch disconnected.' : 'JSearch key saved. Use Search JSearch now when you want new results.');
      if (result) setKey('');
    } finally { setSaving(false); }
  }
  return <section className="card job-source-settings">
    <div className="card-heading"><div><div className="eyebrow">OPTIONAL JOB SEARCH</div><h2>More jobs across Europe</h2></div><span className="badge">{provider?.configured ? 'KEY SAVED' : 'OPTIONAL'}</span></div>
    <p className="settings-description">Bundesagentur für Arbeit, Arbeitnow, Himalayas, Remote OK and Jobicy work without an account or a personal API key. Remote feeds refresh at most once a day. Add JSearch to search more publishers and employer sites, using the same providers as Dossier.</p>
    <p className="form-help"><a href="https://himalayas.app/api" target="_blank" rel="noreferrer">Himalayas</a> offers an optional key for higher rate limits. <a href="https://remoteok.com/faq" target="_blank" rel="noreferrer">Remote OK</a> has a public JSON feed. <a href="https://jobicy.com/jobs-rss-feed" target="_blank" rel="noreferrer">Jobicy</a> needs a paid key only for direct employer application links. Atlas uses their public feeds and links to the original listings. Remote jobs may still have country or timezone restrictions.</p>
    <p className="form-help"><a href="https://www.openwebninja.com/api/jsearch" target="_blank" rel="noreferrer">Get an OpenWeb Ninja key</a> and select its Free plan: 200 requests a month, no credit card required. Atlas caches each search for 24 hours and stops at 180 requests per calendar month. Your key stays on this Mac and is never shown again.</p>
    <form onSubmit={event => { event.preventDefault(); save(); }}>
      <div className="job-source-fields"><label>Key provider<select value={host} onChange={event => setHost(event.target.value)}><option value="openwebninja">OpenWeb Ninja</option><option value="rapidapi">RapidAPI</option></select></label><label>{provider?.configured ? 'Replace saved key (optional)' : 'JSearch API key'}<input type="password" autoComplete="new-password" aria-describedby="jsearch-key-status" value={key} placeholder={provider?.configured ? '•••••••••••• · key saved' : 'Paste your API key'} onChange={event => setKey(event.target.value)} /></label></div>
      <p id="jsearch-key-status" className="form-help" role="status">{provider?.configured ? `Your ${provider.host === 'rapidapi' ? 'RapidAPI' : 'OpenWeb Ninja'} key is saved on this Mac and stays saved after updates and restarts. Leave this field empty to keep it; enter a new key only to replace it.` : 'No key is saved. Paste a key and choose Save key to connect JSearch.'}</p>
      <p className="form-help">{provider?.requests || 0} / {provider?.monthly_limit || 180} Atlas requests this month. Search terms and locations are sent to your chosen provider. Your profile and chats stay local. RapidAPI plan limits may differ.</p>
      <div className="button-row"><button className="button secondary" type="submit" disabled={saving || !key.trim()}>{saving ? 'Saving…' : 'Save key'}</button>{provider?.configured && <button type="button" className="text-button" disabled={saving} onClick={() => save(true)}>Disconnect JSearch</button>}</div>
    </form>
    <div className="job-manual-search"><p className="form-help"><strong>Manual searches only.</strong> Opening Atlas, restarting after updates, refreshing sources and scheduled scans use saved JSearch results without spending credits.</p><p className="form-help">A manual search may use up to {provider?.search_count || 0} requests. Searches cached within the last 24 hours are reused.</p><button className="button secondary" disabled={!provider?.configured || !provider?.search_count || refresh?.running || saving} onClick={() => act('/api/jobs/jsearch', {}, 'JSearch requested. Existing results stay visible while sources refresh.')}>{refresh?.running ? 'Sources are refreshing…' : 'Search JSearch now'}</button></div>
  </section>;
}
