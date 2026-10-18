import React, { useState } from 'react';
import { ArrowClockwiseIcon, CheckIcon, SparkleIcon } from '@phosphor-icons/react';
import Markdown from './Markdown.jsx';
import { niceDate } from './format.js';
import './market.css';

const pct = value => `${Math.round(value * 100)}%`;
const hourly = value => `€${value.toFixed(value % 1 ? 2 : 0)}`;
const yearly = value => `€${Math.round(value / 1000)}K`;
const share = (part, whole) => whole ? pct(part / whole) : '—';
const running = run => run && !['done', 'error', 'cancelled'].includes(run.status);

function Tile({ label, value, note }) { return <div className="market-tile"><span>{label}</span><strong>{value}</strong><small>{note}</small></div>; }

function payTile(spread, format, missing) {
  if (!spread) return { value: 'Not stated', note: missing };
  return { value: format(spread.median), note: `${spread.n >= 4 ? 'Middle half' : 'Range'} ${format(spread.low)}–${format(spread.high)} · ${spread.n} posting${spread.n === 1 ? '' : 's'}` };
}

// One hue, values at the tips, a tooltip on hover and keyboard focus, and a table twin.
function BarCard({ title, label, note, rows, columns, children }) {
  const [table, setTable] = useState(false), [tip, setTip] = useState(null);
  const max = Math.max(1, ...rows.map(row => row.value));
  return <section className="card market-chart">
    <div className="card-heading"><div><div className="eyebrow">{label}</div><h2>{title}</h2></div><button className="text-button" aria-pressed={table} onClick={() => setTable(!table)}>{table ? 'View as chart' : 'View as table'}</button></div>
    {note && <p className="market-note">{note}</p>}
    {!rows.length ? <p className="muted">Nothing to show yet.</p> : table ? <div className="table-wrap"><table><thead><tr>{columns.map(([name]) => <th key={name}>{name}</th>)}</tr></thead><tbody>{rows.map(row => <tr key={row.name}>{columns.map(([name, cell]) => <td key={name}>{cell(row)}</td>)}</tr>)}</tbody></table></div>
      : <ul className="bar-list" onMouseLeave={() => setTip(null)}>{rows.map((row, index) => <li key={row.name} tabIndex={0} aria-label={`${row.name}: ${row.display}. ${row.tip}`} onMouseEnter={() => setTip(index)} onFocus={() => setTip(index)} onBlur={() => setTip(null)}>
        <span className="bar-name">{row.name}{row.mark && <small><CheckIcon size={11} weight="bold" aria-hidden="true" />{row.mark}</small>}</span>
        <span className="bar-track"><span className="bar-fill" style={{ width: `${Math.max(1.5, row.value / max * 100)}%` }} /></span>
        <span className="bar-value">{row.display}</span>
        {tip === index && <span className="bar-tip" role="tooltip">{row.tip}</span>}
      </li>)}</ul>}
    {children}
  </section>;
}

function Takeaways({ data, act }) {
  const run = data.tasks?.market, note = data.market_note, jobs = data.job_market.total;
  const stale = note && note.refreshed_at !== data.refreshed_at;
  return <section className="card market-takeaways">
    <div className="card-heading"><div><div className="eyebrow">WITH ATLAS</div><h2>What this means for you</h2></div><SparkleIcon size={19} weight="bold" aria-hidden="true" /></div>
    {running(run) ? (run.text ? <Markdown>{run.text}</Markdown> : <div className="thinking"><span className="dot pulse" />{run.status === 'loading' ? 'Getting Gemma ready…' : 'Reading the numbers…'}</div>)
      : note ? <><Markdown>{note.text}</Markdown>{stale && <p className="form-help">Your listings changed since this was written.</p>}</>
      : <p className="market-note">Gemma reads the numbers on this page alongside your profile and suggests what to focus on. It runs on this Mac through Hermes and never changes the counts.</p>}
    {run?.status === 'error' && <p className="form-error">{run.text}</p>}
    <div className="card-footer"><span>{note ? `Written ${niceDate(note.at, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })} from ${note.jobs} roles` : 'Written by local Gemma'}</span><button className="text-button" disabled={data.busy || !jobs} onClick={() => act('/api/market/note', {})}>{note ? 'Explain again' : 'Explain with Gemma'}<ArrowClockwiseIcon size={14} /></button></div>
  </section>;
}

export default function JobMarket({ data, act, navigate }) {
  const market = data.job_market, described = market.described;
  if (!market.total) return <><div className="page-heading"><div><div className="eyebrow">WHAT THE LISTINGS SAY</div><h1>Your job market.</h1></div></div><div className="empty"><h3>No listings yet.</h3><p>{data.refresh.running ? 'Your job sources are being checked.' : 'Refresh your sources to see which roles, skills and pay are out there.'}</p></div></>;
  const student = payTile(market.pay.hourly, hourly, 'No posting lists an hourly rate yet'), salary = payTile(market.pay.annual, yearly, 'No posting lists a salary yet');
  const experience = market.experience;
  return <>
    <div className="page-heading"><div><div className="eyebrow">WHAT THE LISTINGS SAY</div><h1>Your job market.</h1><p>Every figure is counted from the {market.total} roles Atlas found, from {data.home.city} outwards; nothing here is estimated by AI.</p></div><button className="button secondary" disabled={data.refresh.running} onClick={() => act('/api/refresh', {})}><ArrowClockwiseIcon size={15} />{data.refresh.running ? 'Refreshing…' : 'Refresh'}</button></div>
    {market.reading?.running && <div className="refresh-status"><span className="dot pulse" />Reading Bundesagentur job descriptions… {market.reading.fetched} checked</div>}
    <div className="market-tiles">
      <Tile label="Roles found" value={market.total.toLocaleString('en-GB')} note={`${market.students} student roles · ${described} with a description`} />
      <Tile label="Student pay per hour" value={student.value} note={student.note} />
      <Tile label="Full-time salary per year" value={salary.value} note={salary.note} />
      <Tile label="German required" value={share(market.language.german_required, described)} note={`${market.language.german_required} of ${described} described postings`} />
    </div>
    <div className="market-grid">
      <Takeaways data={data} act={act} />
      <BarCard title="Types of roles" label="BY JOB TITLE" note="Grouped from each title; hover a bar for the skills that group asks for most."
        rows={market.families.map(row => ({ ...row, value: row.count, display: String(row.count), tip: `${row.count} roles, ${row.students} for students${row.top_skills.length ? `. Often asks for ${row.top_skills.join(', ')}` : ''}.` }))}
        columns={[['Role type', row => row.name], ['Roles', row => row.count], ['Student roles', row => row.students], ['Common skills', row => row.top_skills.join(', ') || '—'], ['Examples', row => row.jobs.map(job => job.title_en || job.title).join(' · ')]]} />
    </div>
    <BarCard title="Skills employers ask for" label="FROM THE DESCRIPTIONS" note={`Share of the ${described} postings with a description that mention each skill.${market.profile_skills.length ? '' : ' Add your skills to your profile in Settings to see which ones you already cover.'}`}
      rows={market.skills.map(row => ({ ...row, value: row.share, display: pct(row.share), mark: row.have ? 'On your profile' : '', tip: `${row.count} of ${described} postings mention ${row.name}.` }))}
      columns={[['Skill', row => row.name], ['Postings', row => row.count], ['Share', row => pct(row.share)], ['On your profile', row => row.have ? 'Yes' : 'No']]}>
      {market.gaps.length > 0 && <p className="market-gaps"><strong>Worth adding next:</strong> {market.gaps.join(', ')}. Each appears in at least one in ten postings, and your profile doesn’t mention it yet.</p>}
    </BarCard>
    <div className="market-grid three">
      <BarCard title="Experience asked for" label="YEARS" note={experience.known ? `${experience.known} postings say how much experience they want${experience.median !== null ? `; the median is ${experience.median} years` : ''}.` : 'No posting states the years of experience yet.'}
        rows={experience.known ? experience.buckets.map(row => ({ ...row, value: row.count, display: String(row.count), tip: `${row.count} postings ask for ${row.name} of experience.` })) : []}
        columns={[['Experience', row => row.name], ['Postings', row => row.count]]} />
      <BarCard title="Seniority" label="FROM TITLES & REQUIREMENTS"
        rows={market.levels.map(row => ({ ...row, value: row.count, display: String(row.count), tip: `${row.count} of ${market.total} roles (${share(row.count, market.total)}).` }))}
        columns={[['Level', row => row.name], ['Roles', row => row.count], ['Share', row => share(row.count, market.total)]]} />
      <BarCard title="Where the roles are" label="TOP CITIES"
        rows={market.cities.map(row => ({ ...row, value: row.count, display: String(row.count), tip: `${row.count} roles in ${row.name}.` }))}
        columns={[['City', row => row.name], ['Roles', row => row.count]]} />
    </div>
    <div className="market-grid">
      <section className="card"><div className="card-heading"><div><div className="eyebrow">WHAT POSTINGS SAY</div><h2>Pay in the listings</h2></div></div>
        {market.pay.examples.length ? <div className="table-wrap"><table><thead><tr><th>Role</th><th>Company</th><th>Pay</th></tr></thead><tbody>{market.pay.examples.map(row => <tr key={row.id}><td>{row.title}</td><td>{row.company}</td><td>{row.period === 'hour' ? `${hourly(row.low)}${row.high !== row.low ? `–${hourly(row.high)}` : ''} / hour` : `${yearly(row.low)}${row.high !== row.low ? `–${yearly(row.high)}` : ''} / year`}</td></tr>)}</tbody></table></div>
          : <p className="muted">None of the descriptions state pay yet. German postings often leave it out; Werkstudent roles usually pay by the hour.</p>}
        <p className="form-help">{market.pay.known} of {market.total} roles state pay. Monthly figures are shown ×12. Check the listing before relying on a number.</p>
      </section>
      <section className="card"><div className="card-heading"><div><div className="eyebrow">LANGUAGE & FLEXIBILITY</div><h2>What the roles expect</h2></div></div>
        <dl className="market-facts">
          <div><dt>German required</dt><dd>{share(market.language.german_required, described)}<small>{market.language.german_required} of {described} described</small></dd></div>
          <div><dt>Posting written in German</dt><dd>{share(market.language.posting_in_german, described)}<small>{market.language.posting_in_german} of {described}</small></dd></div>
          <div><dt>Posting in English</dt><dd>{share(market.language.english, described)}<small>{market.language.english} of {described}</small></dd></div>
          <div><dt>Remote or hybrid{market.remote > 0 && <button className="text-button" onClick={() => navigate('remote')}>See remote roles</button>}</dt><dd>{share(market.remote, market.total)}<small>{market.remote} of {market.total} roles</small></dd></div>
          <div><dt>Visa sponsorship listed</dt><dd>{share(market.visa, market.total)}<small>{market.visa} of {market.total} roles</small></dd></div>
        </dl>
        {market.companies.length > 0 && <><h3 className="market-subhead">Hiring more than once</h3><div className="tags">{market.companies.map(row => <span className="badge" key={row.name}>{row.name} · {row.count}</span>)}</div></>}
      </section>
    </div>
  </>;
}
