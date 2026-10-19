import React, { useMemo } from 'react';
import { XIcon } from '@phosphor-icons/react';
import { activeJobFilters, jobFacets, jobSorts, postedOptions, roleOptions } from './job-filters.js';

export default function JobFilters({ jobs, filters, saved, today, original, setOriginal, set, clear }) {
  const facets = useMemo(() => jobFacets(jobs, filters, saved, today), [jobs, filters, saved, today]);
  const option = ({ value, count }) => <option key={value} value={value}>{value} ({count})</option>;
  // Keep a chosen value listed even when other filters leave it with no matches.
  const keep = (rows, value) => !value || value === 'all' || rows.some(row => row.value === value) ? rows : [{ value, count: 0 }, ...rows];
  const label = Object.fromEntries(roleOptions);
  return <div className="event-filter-panel" aria-label="Job filters">
    <div className="event-chip-row" role="group" aria-label="Posted">{postedOptions.map(([value, text]) => <button key={value} className={`event-chip ${filters.posted === value ? 'active' : ''}`} aria-pressed={filters.posted === value} onClick={() => set('posted', value)}>{text}</button>)}</div>
    <div className="event-chip-row" role="group" aria-label="Kind of role"><button className={`event-chip ${filters.group === 'all' ? 'active' : ''}`} aria-pressed={filters.group === 'all'} onClick={() => set('group', 'all')}>All roles <small>{facets.total}</small></button>{facets.groups.map(({ value, count }) => <button key={value} className={`event-chip ${filters.group === value ? 'active' : ''}`} aria-pressed={filters.group === value} onClick={() => set('group', filters.group === value ? 'all' : value)}>{label[value]} <small>{count}</small></button>)}</div>
    <div className="event-filter-selects job-filter-selects">
      <label>Country<select value={filters.jobCountry} onChange={e => set('jobCountry', e.target.value)}><option value="all">All countries</option>{keep(facets.countries, filters.jobCountry).map(option)}</select></label>
      <label>City<select value={filters.jobCity} onChange={e => set('jobCity', e.target.value)}><option value="all">{filters.jobCountry === 'all' ? 'All cities' : `All of ${filters.jobCountry}`}</option>{keep(facets.cities, filters.jobCity).map(option)}</select></label>
      <label>Job field<select value={filters.field} onChange={e => set('field', e.target.value)}><option value="all">All fields</option>{keep(facets.fields, filters.field).map(option)}</select></label>
      <label>Job board<select value={filters.source} onChange={e => set('source', e.target.value)}><option value="all">All job boards</option>{keep(facets.sources, filters.source).map(option)}</select></label>
      <label>Order<select value={filters.sort} onChange={e => set('sort', e.target.value)}>{jobSorts.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></label>
    </div>
    <div className="job-filter-checks"><label className="check-label"><input type="checkbox" checked={filters.hideSenior} onChange={e => set('hideSenior', e.target.checked)} />Hide senior jobs</label><label className="check-label"><input type="checkbox" checked={original} onChange={e => setOriginal(e.target.checked)} />Original job titles</label></div>
    {activeJobFilters(filters) > 0 && <button className="text-button event-filter-clear" onClick={clear}><XIcon size={13} />Clear job filters</button>}
  </div>;
}
