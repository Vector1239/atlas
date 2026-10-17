import React, { useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { ArrowClockwiseIcon, BriefcaseIcon, CalendarBlankIcon, MapPinIcon, SlidersHorizontalIcon, XIcon } from '@phosphor-icons/react';
import { JobListing } from './JobListing.jsx';
import { EventListing } from './EventListing.jsx';
import { initialFilters, selectExplore, groupPlaces, placeKey, inBounds, validLocation } from './explore-filters.js';
import { safeLink } from './format.js';
import './explore.css';

const presets = { trier: [[49.15, 5.65], [50.5, 8.1]], germany: [[47.1, 5.8], [55.05, 15.2]], europe: [[37.5, -10.1], [56, 18]] };
function DiscoveryMap({ groups, selected, onSelect, onBounds, scope, focus }) {
  const host = useRef(null), map = useRef(null), layer = useRef(null), callbacks = useRef({ onSelect, onBounds });
  const [tileError, setTileError] = useState(false);
  callbacks.current = { onSelect, onBounds };
  useEffect(() => {
    const instance = L.map(host.current, { scrollWheelZoom: false, minZoom: 3, maxZoom: 16 }); map.current = instance;
    instance.attributionControl.setPrefix(false);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors', keepBuffer: 1 }).on('tileerror', () => setTileError(true)).on('tileload', () => setTileError(false)).addTo(instance);
    layer.current = L.layerGroup().addTo(instance);
    const changed = () => { const b = instance.getBounds(); callbacks.current.onBounds({ north: b.getNorth(), south: b.getSouth(), east: b.getEast(), west: b.getWest() }); };
    instance.on('moveend', changed);
    instance.fitBounds(presets.trier, { padding: [35, 35], animate: false });
    const resize = new ResizeObserver(() => instance.invalidateSize()); resize.observe(host.current);
    return () => { resize.disconnect(); instance.remove(); map.current = null; };
  }, []);
  useEffect(() => { map.current?.fitBounds(scope.bounds || presets[scope.name], { padding: [35, 35], maxZoom: 10, animate: false }); }, [scope]);
  useEffect(() => { if (focus) map.current?.setView([focus.lat, focus.lon], 10, { animate: false }); }, [focus]);
  useEffect(() => {
    if (!layer.current) return;
    layer.current.clearLayers();
    groups.forEach(group => {
      const element = document.createElement('span'); element.textContent = String(group.jobs + group.events);
      const marker = L.marker([group.location.lat, group.location.lon], { title: `${group.city}: ${group.jobs} jobs, ${group.events} events. City centre, approximate.`, keyboard: true,
        icon: L.divIcon({ className: `explore-pin ${group.jobs && group.events ? 'mixed' : group.events ? 'events' : 'jobs'} ${selected === group.key ? 'selected' : ''}`, html: element, iconSize: [38, 38], iconAnchor: [19, 19] }) });
      const tip = document.createElement('span'); tip.textContent = `${group.city} · ${group.jobs} jobs · ${group.events} events`;
      marker.bindTooltip(tip, { direction: 'top' }).on('click', () => callbacks.current.onSelect(group)).addTo(layer.current);
    });
  }, [groups, selected]);
  return <div className="explore-map-wrap"><div className="explore-map" ref={host} role="region" aria-label="Interactive jobs and events map. Use arrow keys to pan, plus and minus to zoom. City buttons below also select locations." />{tileError && <div className="map-error" role="status">Map tiles are unavailable. Pins, filters and listings still work.</div>}</div>;
}

export default function Explore({ data, act, ask, initialKind = 'all' }) {
  const [filters, setFilters] = useState({ ...initialFilters, kind: initialKind }), [bounds, setBounds] = useState(null), [inView, setInView] = useState(true), [selected, setSelected] = useState(null), [scope, setScope] = useState({ name: 'trier' }), [focus, setFocus] = useState(null), [moreFilters, setMoreFilters] = useState(false), [original, setOriginal] = useState(false), [limit, setLimit] = useState(20);
  const set = (key, value) => {
    setFilters(previous => ({ ...previous, [key]: value })); setSelected(null); setLimit(20);
    if (key === 'city' && value !== 'all') {
      const item = [...data.jobs, ...(data.events?.items || [])].find(item => item.city === value && validLocation(item.location));
      if (item) setFocus({ ...item.location });
    }
  };
  const candidates = useMemo(() => selectExplore(data, filters), [data, filters]);
  const groups = useMemo(() => groupPlaces(candidates), [candidates]);
  const unmapped = candidates.filter(item => !validLocation(item.location)).length;
  const visible = candidates.filter(item => (!inView || inBounds(item.location, bounds)) && (!selected || placeKey(item) === selected));
  const shownGroups = groups.filter(group => !inView || inBounds(group.location, bounds));
  const pending = data.jobs.filter(job => job.translation_needed).length;
  function choose(group) { setSelected(previous => previous === group.key ? null : group.key); setFocus({ ...group.location }); setLimit(20); }
  function revealMatches() {
    const locations = candidates.filter(item => validLocation(item.location)).map(item => [item.location.lat, item.location.lon]);
    setSelected(null);
    if (locations.length) { setInView(true); setScope({ name: 'matches', bounds: L.latLngBounds(locations) }); }
    else setInView(false);
  }
  function reset() { setFilters({ ...initialFilters }); setSelected(null); setInView(true); setScope({ name: 'trier' }); setLimit(20); }
  return <>
    <div className="page-heading discovery-heading"><div><div className="eyebrow">OPPORTUNITIES & OCCASIONS</div><h1>Find your place.</h1><p>Jobs and things to do, together on one map.</p></div><button className="button secondary" disabled={data.refresh.running} onClick={() => act('/api/refresh', {})}><ArrowClockwiseIcon size={16} />{data.refresh.running ? 'Refreshing…' : 'Refresh sources'}</button></div>
    <section className="explore-toolbar" aria-label="Explore filters"><div className="explore-toolbar-top"><div className="tabs" aria-label="What to explore">{[['all', 'Everything'], ['jobs', 'Jobs'], ['events', 'Events']].map(([value, label]) => <button key={value} className={filters.kind === value ? 'active' : ''} aria-pressed={filters.kind === value} onClick={() => set('kind', value)}>{label}</button>)}</div><input className="search" aria-label="Search jobs and events" placeholder="Role, event, company or city…" value={filters.search} onChange={e => set('search', e.target.value)} /><button className="button secondary" aria-expanded={moreFilters} onClick={() => setMoreFilters(!moreFilters)}><SlidersHorizontalIcon size={16} />Filters</button></div>
      <div className="explore-quick-filters"><label>Distance from Trier<select value={filters.distance} onChange={e => set('distance', e.target.value)}><option value="any">Any distance</option>{[10,25,50,75,100,150].map(km => <option key={km} value={km}>Within {km} km</option>)}</select></label><label>City<select value={filters.city} onChange={e => set('city', e.target.value)}><option value="all">All cities</option>{[...new Set([...data.jobs, ...(data.events?.items || [])].map(item => item.city))].sort().map(city => <option key={city}>{city}</option>)}</select></label><label>Events happening<select value={filters.period} onChange={e => set('period', e.target.value)}><option value="all">Any upcoming date</option>{[7,30,90].map(days => <option key={days} value={days}>Next {days} days</option>)}</select></label><label className="check-label view-filter"><input type="checkbox" checked={inView} onChange={e => { setInView(e.target.checked); setSelected(null); }} />Only this map area</label><button className="text-button" onClick={reset}>Reset</button></div>
      {moreFilters && <div className="explore-more-filters"><label>Job group<select value={filters.group} onChange={e => set('group', e.target.value)}><option value="all">All roles</option><option value="student">Student roles</option><option value="saved">Saved roles</option></select></label><label>Job board<select value={filters.source} onChange={e => set('source', e.target.value)}><option value="all">All job boards</option>{(data.job_sources || []).map(source => <option key={source.name}>{source.name}</option>)}</select></label><label>Workplace<select value={filters.workplace} onChange={e => set('workplace', e.target.value)}><option value="all">Any workplace</option><option value="remote">Remote mentioned</option></select></label><label>Posting language<select value={filters.language} onChange={e => set('language', e.target.value)}><option value="all">Any / unknown</option><option value="english">English detected</option><option value="german">German detected</option></select></label><label>Event type<select value={filters.category} onChange={e => set('category', e.target.value)}><option value="all">All types</option>{[...new Set(data.events.items.map(event => event.category))].sort().map(category => <option key={category}>{category}</option>)}</select></label><label>Job order<select value={filters.sort} onChange={e => set('sort', e.target.value)}><option value="distance">Nearest first</option><option value="newest">Newest first</option><option value="student">Student roles first</option></select></label><label className="check-label"><input type="checkbox" checked={filters.hideSenior} onChange={e => set('hideSenior', e.target.checked)} />Hide senior jobs</label><label className="check-label"><input type="checkbox" checked={original} onChange={e => setOriginal(e.target.checked)} />Original job titles</label></div>}
    </section>
    <div className="explore-layout"><section className="map-panel" aria-label="Discover by location"><div className="map-heading"><div><MapPinIcon size={18} weight="bold" /><strong>Follow your curiosity.</strong></div><div className="map-presets">{[['trier','Around Trier'],['germany','Germany'],['europe','Europe']].map(([key,label]) => <button key={key} className={scope.name === key ? 'active' : ''} onClick={() => { setScope({ name: key }); setSelected(null); }}>{label}</button>)}</div></div>
      <DiscoveryMap groups={groups} selected={selected} onSelect={choose} onBounds={setBounds} scope={scope} focus={focus} />
      <div className="map-legend"><span><i className="legend-jobs" />Jobs</span><span><i className="legend-events" />Events</span><span><i className="legend-mixed" />Both</span><small>Numbers = listings · City centres, approximate</small></div>
      <div className="map-cities" aria-label="Select a city">{shownGroups.map(group => <button key={group.key} aria-pressed={selected === group.key} className={selected === group.key ? 'active' : ''} onClick={() => choose(group)}>{group.city}<span>{group.jobs + group.events}</span></button>)}</div>
      <p className="map-credit">City coordinates: <a href="https://open-meteo.com/en/docs/geocoding-api" target="_blank" rel="noreferrer">Open-Meteo / GeoNames</a>. Pins indicate the listing’s city, not an exact address. Map tiles need internet.</p>
    </section><section className="explore-results" aria-label="Jobs and events results"><div className="explore-result-heading"><div><strong>{visible.length} {visible.length === 1 ? 'result' : 'results'}</strong><span><BriefcaseIcon size={13} />{visible.filter(item => item.kind === 'job').length} jobs <CalendarBlankIcon size={13} />{visible.filter(item => item.kind === 'event').length} events</span></div>{selected && <button className="text-button" onClick={() => setSelected(null)}><XIcon size={14} />Clear city</button>}</div>
      <p className="explore-result-note">{inView ? 'Move or zoom the map to change these results.' : 'Showing all matching locations, including unplaced listings.'} {unmapped > 0 && `${unmapped} without a verified pin${inView ? ' — untick “Only this map area” to include them' : ''}.`}</p>
      <div className="explore-result-list">{visible.slice(0,limit).map(item => <div className={`explore-listing ${item.kind}`} key={item.key}><div className="listing-kind">{item.kind === 'job' ? <BriefcaseIcon size={14} /> : <CalendarBlankIcon size={14} />}{item.kind === 'job' ? 'JOB' : 'EVENT'}{item.location && <button className="text-button" onClick={() => { setSelected(placeKey(item)); setFocus({ ...item.location }); }}>{item.city}<MapPinIcon size={13} /></button>}</div>{item.kind === 'job' ? <JobListing job={item} original={original} data={data} act={act} ask={ask} /> : <EventListing event={item} />}</div>)}</div>
      {!visible.length && <div className="empty"><MapPinIcon size={30} /><h3>Nothing in this view yet.</h3><p>{candidates.length ? `${candidates.length} matches are outside this view or have no verified pin.` : 'Try a wider date range or different filters.'}</p>{!!candidates.length && <button className="button secondary" onClick={revealMatches}>Show matching locations</button>}<button className="text-button" onClick={reset}>Reset the view</button></div>}
      {visible.length > limit && <button className="button secondary load-listings" onClick={() => setLimit(limit + 20)}>Show more ({visible.length - limit} remaining)</button>}
    </section></div>
    <div className="explore-context"><p><strong>Know what you’re seeing.</strong> Jobs come from {(data.job_sources || []).map(source => `${source.name} (${source.count})`).join(', ')}. {data.adzuna_key_missing && 'Adzuna needs an API key.'} English titles don’t establish English-only eligibility. A job radius uses the board’s distance from Trier; an event radius uses straight-line distance between city centres.</p><p>Events are a dated selection from official calendars, checked {data.events.checked_at}. Check the organiser before travelling. {data.events.calendars.map(calendar => <a key={calendar.url} href={safeLink(calendar.url)} target="_blank" rel="noreferrer">{calendar.name} ↗ </a>)}</p></div>
    {!!pending && filters.kind !== 'events' && <div className="translation-notice"><p>{pending} job titles await English translation. {data.model.ready ? 'Translate with local Qwen.' : 'Qwen is paused; originals remain visible.'}</p><button className="button secondary" disabled={!data.model.ready || data.busy} onClick={() => act('/api/jobs/translate', {})}>{data.translation.running && data.translation.kind === 'jobs' ? `Translating… ${data.translation.completed} done` : 'Translate job titles'}</button></div>}
    {data.translation.kind === 'jobs' && data.translation.error && <p className="form-error" role="alert">{data.translation.error}</p>}
  </>;
}
