import React, { useState } from 'react';

export default function EventSources({ provider, act }) {
  const [key, setKey] = useState(''), [saving, setSaving] = useState(false);
  async function save(remove = false) {
    setSaving(true);
    try {
      const result = await act('/api/events/provider', { key: remove ? '' : key.trim() }, remove ? 'Ticketmaster disconnected.' : 'Ticketmaster key saved. Events are loading in the background.');
      if (result) setKey('');
    } finally { setSaving(false); }
  }
  const fetched = provider?.fetched_at ? new Date(provider.fetched_at).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' }) : '';
  return <section className="card job-source-settings">
    <div className="card-heading"><div><div className="eyebrow">OPTIONAL EVENT SOURCE</div><h2>Events across Germany & Europe</h2></div><span className="badge">{provider?.configured ? `${provider.count} EVENTS` : 'OPTIONAL'}</span></div>
    <p className="settings-description">Add a free Ticketmaster key to see concerts, theatre, comedy, festivals and sports in the next 45 days: within 150 km of home, in 12 German cities (Berlin, Hamburg, Munich, Cologne, Frankfurt, Stuttgart, Düsseldorf, Leipzig, Dresden, Hanover, Nuremberg, Bremen) and in 14 European capitals and big cities. Each event has its venue on the map and links to its Ticketmaster page.</p>
    <p className="form-help"><a href="https://developer-acct.ticketmaster.com/user/register" target="_blank" rel="noreferrer">Create a free Ticketmaster developer account</a> and copy the Consumer Key of its default app: 5,000 requests a day, no payment details. Atlas uses about 30 requests every 12 hours. Your key stays on this Mac and is never shown again.</p>
    <form onSubmit={event => { event.preventDefault(); save(); }}>
      <label className="event-source-field">{provider?.configured ? 'Replace saved key (optional)' : 'Ticketmaster Consumer Key'}<input type="password" autoComplete="new-password" value={key} placeholder={provider?.configured ? '•••••••••••• · key saved' : 'Paste your Consumer Key'} onChange={event => setKey(event.target.value)} /></label>
      <p className="form-help" role="status">{provider?.running ? 'Loading events…' : provider?.configured ? (fetched ? `Last loaded ${fetched}. ` : 'Not loaded yet. ') + (provider.error ? `Some searches failed: ${provider.error}` : '') : 'No key is saved. The dated selection from official calendars still shows without one.'}</p>
      <div className="button-row"><button className="button secondary" type="submit" disabled={saving || !key.trim()}>{saving ? 'Saving…' : 'Save key'}</button>{provider?.configured && <button type="button" className="text-button" disabled={saving} onClick={() => save(true)}>Disconnect Ticketmaster</button>}</div>
    </form>
  </section>;
}
