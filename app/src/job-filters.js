import { cityDistance } from './geo.js';

// The Jobs tab's own filters: when a role was posted, what kind of role, place, field and job board, each with live counts.
export const postedOptions = [['any', 'Any time'], ['1', 'Today'], ['3', 'Last 3 days'], ['7', 'Last 7 days'], ['14', 'Last 14 days']];
export const roleOptions = [['student', 'Student roles'], ['english', 'English posting'], ['remote', 'Remote'], ['saved', 'Saved']];
export const jobSorts = [['distance', 'Nearest home first'], ['newest', 'Newest first'], ['student', 'Student roles first']];

// The board's own distance from Trier when it gives one, otherwise the distance between city centres.
export const jobDistance = job => job.distance_from_trier ?? cityDistance(job.location);
export const jobCountry = job => job.country_name || (job.city === 'Remote' ? 'Remote' : 'Germany');
export const jobPlaceLabel = job => job.city === 'Remote' ? 'Remote' : [job.city, jobCountry(job)].filter(Boolean).join(', ');

const iso = date => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
function postedSince(posted, today) {
  if (!posted || posted === 'any' || !today) return null;
  const date = new Date(`${today}T12:00:00`); date.setDate(date.getDate() - Number(posted) + 1);
  return iso(date);
}

export function matchesJob(job, filters, saved = [], today = '', skip = '') {
  const text = `${job.title} ${job.title_en || ''} ${job.company} ${job.where} ${job.city} ${job.source_label}`.toLowerCase();
  const since = postedSince(filters.posted, today), country = filters.country || 'all';
  return text.includes((filters.search || '').trim().toLowerCase())
    && (skip === 'group' || filters.group !== 'student' || job.flags.includes('student-job'))
    && (skip === 'group' || filters.group !== 'saved' || saved.includes(job.id))
    && (skip === 'group' || filters.group !== 'remote' || job.remote)
    && (skip === 'group' || filters.group !== 'english' || job.flags.includes('english'))
    && (filters.distance === 'any' || (jobDistance(job) ?? Infinity) <= Number(filters.distance))
    && (skip === 'city' || skip === 'country' || filters.city === 'all' || job.city === filters.city)
    && (skip === 'country' || country === 'all' || jobCountry(job) === country)
    && (skip === 'field' || !filters.field || filters.field === 'all' || job.field === filters.field)
    && (skip === 'source' || filters.source === 'all' || job.source_label === filters.source)
    && (filters.workplace !== 'remote' || job.remote)
    && (filters.language === 'all' || job.flags.includes(filters.language === 'english' ? 'english' : 'posting-in-german'))
    && (!since || !!job.posted && job.posted.slice(0, 10) >= since)
    && (!filters.hideSenior || !job.flags.includes('senior'));
}

const newest = (a, b) => (Date.parse(b.posted) || 0) - (Date.parse(a.posted) || 0);
export function selectJobs(jobs, filters, saved = [], today = '') {
  const result = jobs.filter(job => matchesJob(job, filters, saved, today));
  if (filters.sort === 'distance' && filters.nearestByCity) {
    // Like events: rank whole cities by distance from home, newest roles first within each city.
    const near = new Map();
    for (const job of result) near.set(jobPlaceLabel(job), Math.min(near.get(jobPlaceLabel(job)) ?? Infinity, jobDistance(job) ?? Infinity));
    return result.sort((a, b) => near.get(jobPlaceLabel(a)) - near.get(jobPlaceLabel(b)) || jobPlaceLabel(a).localeCompare(jobPlaceLabel(b)) || newest(a, b));
  }
  return result.sort((a, b) => {
    if (filters.sort === 'newest') return newest(a, b);
    if (filters.sort === 'student') {
      const priority = Number(b.flags.includes('student-job')) - Number(a.flags.includes('student-job'));
      if (priority) return priority;
    }
    return (jobDistance(a) ?? Infinity) - (jobDistance(b) ?? Infinity) || a.title.localeCompare(b.title);
  });
}

// The Jobs tab reads its own place, field and posted filters; the Everything view keeps the shared city filter and ignores them.
export function jobFilterView(filters) {
  return filters.kind === 'jobs'
    ? { ...filters, city: filters.jobCity || 'all', country: filters.jobCountry || 'all', language: 'all', nearestByCity: true }
    : { ...filters, country: 'all', field: 'all', posted: 'any' };
}

const tally = (rows, value) => {
  const counts = new Map();
  for (const row of rows) { const key = value(row); if (key) counts.set(key, (counts.get(key) || 0) + 1); }
  return [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([value, count]) => ({ value, count }));
};

// Each facet counts what the other active filters leave, so a choice never leads to zero results.
export function jobFacets(jobs, filters, saved = [], today = '') {
  const view = jobFilterView(filters), without = skip => jobs.filter(job => matchesJob(job, view, saved, today, skip));
  const anyGroup = without('group'), inCountry = without('city').filter(job => view.country === 'all' || jobCountry(job) === view.country);
  return {
    total: anyGroup.length,
    groups: roleOptions.map(([value]) => ({ value, count: anyGroup.filter(job => matchesJob(job, { ...view, group: value }, saved, today)).length })),
    countries: tally(without('country'), jobCountry), cities: tally(inCountry, job => job.city),
    fields: tally(without('field'), job => job.field), sources: tally(without('source'), job => job.source_label),
  };
}

export const activeJobFilters = filters => ['posted', 'group', 'jobCountry', 'jobCity', 'field', 'source'].filter(key => filters[key] && !['all', 'any'].includes(filters[key])).length + Number(!!filters.hideSenior);

// The Jobs tab remembers its filters across pages and restarts, on this Mac only.
const STORE = 'atlas.explore.jobs', remembered = ['posted', 'group', 'jobCountry', 'jobCity', 'field', 'source', 'sort'];
export function savedJobFilters(storage = globalThis.localStorage) {
  try {
    const saved = JSON.parse(storage?.getItem(STORE) || '{}');
    return { ...Object.fromEntries(remembered.filter(key => typeof saved[key] === 'string').map(key => [key, saved[key]])),
      ...(typeof saved.hideSenior === 'boolean' ? { hideSenior: saved.hideSenior } : {}) };
  } catch { return {}; }
}
export function saveJobFilters(filters, storage = globalThis.localStorage) {
  try { storage?.setItem(STORE, JSON.stringify(Object.fromEntries([...remembered, 'hideSenior'].map(key => [key, filters[key]])))); } catch { /* storage unavailable */ }
}

export function distanceLabel(job) {
  if (job.distance_from_trier != null) return `${job.distance_from_trier.toLocaleString('en-GB', { maximumFractionDigits: 1 })} km from Trier · board reported`;
  if (job.distance_km != null && job.distance_origin) return `${job.distance_km} km from ${job.distance_origin}`;
  return 'Distance not provided';
}
