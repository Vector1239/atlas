import { selectJobs } from './job-filters.js';

export const initialFilters = { search: '', kind: 'all', group: 'all', distance: 'any', city: 'all', source: 'all', workplace: 'all', language: 'all', hideSenior: false, sort: 'distance', period: 'all', category: 'all' };
export function filtersForScope(filters, scope) {
  return { ...filters, city: 'all', distance: 'any',
    workplace: scope === 'remote' ? 'remote' : 'all',
    ...(scope === 'remote' ? { kind: 'jobs', sort: 'newest', source: 'all' } : {}) };
}
export const placeKey = item => item.location ? `${item.location.lat},${item.location.lon}` : null;
export function exploreTotals(data) {
  const jobs = (data.jobs || []).length, events = (data.events?.items || []).length;
  return { jobs, events, total:jobs + events };
}
export function validLocation(location) {
  return !!location && Number.isFinite(location.lat) && Number.isFinite(location.lon) && Math.abs(location.lat) <= 90 && Math.abs(location.lon) <= 180;
}
export function cityDistance(location) {
  if (!validLocation(location)) return null;
  const rad = x => x * Math.PI / 180;
  const lat = rad(location.lat - 49.75565), lon = rad(location.lon - 6.63935);
  const a = Math.sin(lat / 2) ** 2 + Math.cos(rad(49.75565)) * Math.cos(rad(location.lat)) * Math.sin(lon / 2) ** 2;
  return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(Math.max(0, 1 - a)));
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
export function selectExplore(data, filters, scope) {
  const sourceJobs = scope === 'remote' ? data.jobs.filter(job => remoteSources.has(job.source || job.source_label)) : data.jobs;
  const jobs = filters.kind === 'events' ? [] : selectJobs(sourceJobs, filters, data.saved_jobs).map(job => ({ ...job, kind: 'job', key: `job:${job.id}` }));
  const cutoff = new Date(`${data.date}T12:00:00`); cutoff.setDate(cutoff.getDate() + Number(filters.period));
  const events = filters.kind === 'jobs' ? [] : (data.events?.items || []).filter(event => {
    const distance = cityDistance(event.location);
    return `${event.title} ${event.city} ${event.venue} ${event.category} ${event.source}`.toLowerCase().includes(filters.search.trim().toLowerCase())
      && (filters.period === 'all' || new Date(`${event.start}T12:00:00`) <= cutoff)
      && (filters.category === 'all' || event.category === filters.category)
      && (filters.city === 'all' || event.city === filters.city)
      && (filters.distance === 'any' || distance !== null && distance <= Number(filters.distance));
  }).map(event => ({ ...event, kind: 'event', key: `event:${event.id}` }));
  // Alternate the two kinds so events don't get buried beneath a full job feed.
  return Array.from({ length: Math.max(jobs.length, events.length) }, (_, i) => [jobs[i], events[i]]).flat().filter(Boolean);
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
