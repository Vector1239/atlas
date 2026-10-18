import React, { useState } from 'react';

export default function JobSources({ provider, act }) {
  const [host, setHost] = useState(provider?.host || 'openwebninja');
  const [key, setKey] = useState(''), [saving, setSaving] = useState(false);
  async function save(remove = false) {
    setSaving(true);
    try {
      const result = await act('/api/jobs/provider', { host, key: remove ? '' : key.trim() }, remove ? 'JSearch disconnected.' : 'JSearch key saved. Refresh sources to find jobs.');
      if (result) setKey('');
    } finally { setSaving(false); }
  }
  return <section className="card job-source-settings">
    <div className="card-heading"><div><div className="eyebrow">OPTIONAL JOB SEARCH</div><h2>More jobs across Europe</h2></div><span className="badge">{provider?.configured ? 'KEY SAVED' : 'OPTIONAL'}</span></div>
    <p className="settings-description">Bundesagentur für Arbeit and Arbeitnow work without an account. Add JSearch to search more publishers and employer sites, using the same providers as Dossier.</p>
    <p className="form-help"><a href="https://www.openwebninja.com/api/jsearch" target="_blank" rel="noreferrer">Get an OpenWeb Ninja key</a> and select its Free plan: 200 requests a month, no credit card required. Atlas caches each search for 24 hours and stops at 180 requests per calendar month. Your key stays on this Mac and is never shown again.</p>
    <form onSubmit={event => { event.preventDefault(); save(); }}>
      <div className="job-source-fields"><label>Key provider<select value={host} onChange={event => setHost(event.target.value)}><option value="openwebninja">OpenWeb Ninja</option><option value="rapidapi">RapidAPI</option></select></label><label>JSearch API key<input type="password" autoComplete="new-password" value={key} placeholder={provider?.configured ? 'Enter a replacement key' : 'Paste your API key'} onChange={event => setKey(event.target.value)} /></label></div>
      <p className="form-help">{provider?.requests || 0} / {provider?.monthly_limit || 180} Atlas requests this month. Search terms and locations are sent to your chosen provider. Your profile and chats stay local. RapidAPI plan limits may differ.</p>
      <div className="button-row"><button className="button secondary" type="submit" disabled={saving || !key.trim()}>{saving ? 'Saving…' : 'Save key'}</button>{provider?.configured && <button type="button" className="text-button" disabled={saving} onClick={() => save(true)}>Disconnect JSearch</button>}</div>
    </form>
  </section>;
}
