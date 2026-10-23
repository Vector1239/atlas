import { jobFilterView, selectJobs } from './job-filters.js';
import { validLocation, cityDistance } from './geo.js';
export { validLocation, cityDistance };
import { matchesEvent } from './event-filters.js';

export const initialFilters = { search: '', kind: 'all', group: 'all', distance: 'any', city: 'all', source: 'all', workplace: 'all', language: 'all', hideSenior: false, sort: 'distance', when: 'any', category: 'all', genre: 'all', country: 'all', eventSort: 'nearest', posted: 'any', jobCountry: 'all', jobCity: 'all', field: 'all' };
export function filtersForScope(filters, scope) {
  return { ...filters, city: 'all', country: 'all', jobCity: 'all', jobCountry: 'all', distance: 'any',
    workplace: scope === 'remote' ? 'remote' : 'all',
    ...(scope === 'remote' ? { kind: 'jobs', sort: 'newest', source: 'all' } : {}) };
}
export const placeKey = item => item.location ? `${item.location.lat},${item.location.lon}` : null;
export function exploreTotals(data) {
  const jobs = (data.jobs || []).length, events = (data.events?.items || []).length;
  return { jobs, events, total:jobs + events };
}
export function inBounds(location, bounds) {
  if (!validLocation(location)) return false;
  if (!bounds) return true;
  const longitude = ((location.lon - bounds.west) % 360 + 360) % 360;
  return location.lat >= bounds.south && location.lat <= bounds.north && (bounds.east - bounds.west >= 360 || longitude <= bounds.east - bounds.west);
}
export function exploreView(items, { inView = true, bounds = null, selected = null } = {}) {
  const result = { visible:[], unplaced:0, outsideArea:0, outsideCity:0 };
  for (const item of items) {
    if (inView && !validLocation(item.location)) result.unplaced++;
    else if (inView && !inBounds(item.location, bounds)) result.outsideArea++;
    else if (selected && placeKey(item) !== selected) result.outsideCity++;
    else result.visible.push(item);
  }
  return result;
}
const remoteSources = new Set(['Himalayas', 'Remote OK', 'Jobicy']);
export const exploreJobs = (data, scope) => scope === 'remote' ? data.jobs.filter(job => remoteSources.has(job.source || job.source_label)) : data.jobs;
export function selectExplore(data, filters, scope) {
  const sourceJobs = exploreJobs(data, scope);
  const jobs = filters.kind === 'events' ? [] : selectJobs(sourceJobs, jobFilterView(filters), data.saved_jobs, data.date).map(job => ({ ...job, kind: 'job', key: `job:${job.id}` }));
  const events = filters.kind === 'jobs' ? [] : (data.events?.items || []).filter(event => {
    const distance = cityDistance(event.location);
    return matchesEvent(event, filters, data.date)
      && (filters.distance === 'any' || distance !== null && distance <= Number(filters.distance));
  }).map(event => ({ ...event, kind: 'event', key: `event:${event.id}` }));
  if (filters.eventSort === 'nearest') {
    // Venues in one city sit a few hundred metres apart, so rank whole cities by distance and keep each city's events in date order.
    const place = event => `${event.city}|${event.country}`, near = new Map();
    for (const event of events) near.set(place(event), Math.min(near.get(place(event)) ?? Infinity, cityDistance(event.location) ?? Infinity));
    events.sort((a, b) => near.get(place(a)) - near.get(place(b)) || place(a).localeCompare(place(b)) || a.start.localeCompare(b.start));
  } else events.sort((a, b) => a.start.localeCompare(b.start));
  // Alternate the two kinds so events don't get buried beneath a full job feed.
  // Listing keys must be unique: React keeps a stale card on screen (a job in the Events list) when two share one.
  const used = new Map();
  return Array.from({ length: Math.max(jobs.length, events.length) }, (_, i) => [jobs[i], events[i]]).flat().filter(Boolean).map(item => {
    const seen = used.get(item.key) || 0;
    used.set(item.key, seen + 1);
    return seen ? { ...item, key: `${item.key}#${seen}` } : item;
  });
}
export function groupPlaces(items) {
  const groups = new Map();
  for (const item of items) {
    if (!validLocation(item.location)) continue;
    const key = placeKey(item);
    if (!groups.has(key)) groups.set(key, { key, location: item.location, city: item.city, jobs: 0, events: 0 });
    groups.get(key)[item.kind === 'job' ? 'jobs' : 'events']++;
  }
  return [...groups.values()];
}
