import React, { useMemo } from 'react';
import { XIcon } from '@phosphor-icons/react';
import { activeEventFilters, eventFacets, eventSorts, whenOptions } from './event-filters.js';

export default function EventFilters({ events, filters, today, set, clear }) {
  const facets = useMemo(() => eventFacets(events, filters, today), [events, filters, today]);
  const total = facets.categories.reduce((sum, row) => sum + row.count, 0);
  const option = ({ value, count }) => <option key={value} value={value}>{value} ({count})</option>;
  // Keep a chosen value listed even when other filters leave it with no matches.
  const keep = (rows, value) => value === 'all' || rows.some(row => row.value === value) ? rows : [{ value, count: 0 }, ...rows];
  return <div className="event-filter-panel" aria-label="Event filters">
    <div className="event-chip-row" role="group" aria-label="When">{whenOptions.map(([value, label]) => <button key={value} className={`event-chip ${filters.when === value ? 'active' : ''}`} aria-pressed={filters.when === value} onClick={() => set('when', value)}>{label}</button>)}</div>
    <div className="event-chip-row" role="group" aria-label="Type of event"><button className={`event-chip ${filters.category === 'all' ? 'active' : ''}`} aria-pressed={filters.category === 'all'} onClick={() => set('category', 'all')}>All types <small>{total}</small></button>{keep(facets.categories, filters.category).map(({ value, count }) => <button key={value} className={`event-chip ${filters.category === value ? 'active' : ''}`} aria-pressed={filters.category === value} onClick={() => set('category', filters.category === value ? 'all' : value)}>{value} <small>{count}</small></button>)}</div>
    <div className="event-filter-selects">
      <label>Country<select value={filters.country} onChange={e => set('country', e.target.value)}><option value="all">All countries</option>{keep(facets.countries, filters.country).map(option)}</select></label>
      <label>City<select value={filters.city} onChange={e => set('city', e.target.value)}><option value="all">{filters.country === 'all' ? 'All cities' : `All of ${filters.country}`}</option>{keep(facets.cities, filters.city).map(option)}</select></label>
      <label>Genre<select value={filters.genre} disabled={!facets.genres.length && filters.genre === 'all'} onChange={e => set('genre', e.target.value)}><option value="all">{filters.category === 'all' ? 'All genres' : `All ${filters.category.toLowerCase()}`}</option>{keep(facets.genres, filters.genre).map(option)}</select></label>
      <label>Order<select value={filters.eventSort} onChange={e => set('eventSort', e.target.value)}>{eventSorts.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
    </div>
    {activeEventFilters(filters) > 0 && <button className="text-button event-filter-clear" onClick={clear}><XIcon size={13} />Clear event filters</button>}
  </div>;
}
