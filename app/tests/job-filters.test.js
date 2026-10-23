import { test } from 'node:test';
import assert from 'node:assert/strict';
import { selectJobs, distanceLabel } from '../src/job-filters.js';

const filters = { search: '', group: 'all', distance: 'any', city: 'all', source: 'all', workplace: 'all', language: 'all', hideSenior: false, sort: 'distance' };
const base = { title: 'Datenanalyst', title_en: 'Data Analyst', company: 'Company', where: 'Trier', city: 'Trier', source_label: 'Bundesagentur', posted: '2026-10-10', remote: false, flags: [] };
const jobs = [
  { ...base, id: 'far', distance_from_trier: 100, flags: ['senior'] },
  { ...base, id: 'unknown', distance_from_trier: null, source_label: 'Arbeitnow', remote: true },
  { ...base, id: 'near', distance_from_trier: 1, flags: ['student-job'], posted: '2026-10-17' },
];

test('distance filter excludes unknowns and orders numeric distances', () => {
  assert.deepEqual(selectJobs(jobs, { ...filters, distance: '25' }).map(j => j.id), ['near']);
  assert.deepEqual(selectJobs(jobs, filters).map(j => j.id), ['near', 'far', 'unknown']);
  assert.equal(distanceLabel(jobs[1]), 'Distance not provided');
});
test('filters combine and searches support translated and original titles', () => {
  assert.equal(selectJobs(jobs, { ...filters, search: 'data analyst', group: 'student', source: 'Bundesagentur', hideSenior: true }).length, 1);
  assert.equal(selectJobs(jobs, { ...filters, search: 'Datenanalyst' }).length, 3);
  assert.equal(selectJobs(jobs, { ...filters, workplace: 'remote', distance: '25' }).length, 0);
});
test('saved jobs respect other filters and English title does not mean English posting', () => {
  assert.deepEqual(selectJobs(jobs, { ...filters, group: 'saved' }, ['far']).map(j => j.id), ['far']);
  assert.equal(selectJobs(jobs, { ...filters, language: 'english' }).length, 0);
  assert.equal(selectJobs(jobs, { ...filters, group: 'saved', hideSenior: true }, ['far']).length, 0);
});
test('newest sorting does not mutate input and empty search resets naturally', () => {
  const before = jobs.map(j => j.id);
  assert.equal(selectJobs(jobs, { ...filters, sort: 'newest' })[0].id, 'near');
  assert.deepEqual(jobs.map(j => j.id), before);
  assert.equal(selectJobs(jobs, { ...filters, search: 'nothing here' }).length, 0);
});

import { activeJobFilters, jobFacets, jobFilterView, savedJobFilters, saveJobFilters } from '../src/job-filters.js';
import { initialFilters, selectExplore } from '../src/explore-filters.js';
const trier = { lat: 49.75565, lon: 6.63935 }, regensburg = { lat: 49.01513, lon: 12.10161 };
const tab = { ...initialFilters, kind: 'jobs' };
const listings = [
  { ...base, id: 'reg-old', city: 'Regensburg', field: 'Software engineering', distance_from_trier: null, location: regensburg, posted: '2026-10-05' },
  { ...base, id: 'reg-new', city: 'Regensburg', field: 'Software engineering', distance_from_trier: null, location: regensburg, posted: '2026-10-19', flags: ['english'] },
  { ...base, id: 'trier', city: 'Trier', field: 'Analytics & BI', distance_from_trier: 2, location: trier, posted: '2026-10-18', flags: ['student-job'] },
  { ...base, id: 'lux', city: 'Luxembourg', country_name: 'Luxembourg', field: 'Analytics & BI', distance_from_trier: null, location: { lat: 49.61, lon: 6.13 }, posted: '2026-10-12' },
];
test('the Jobs tab orders whole cities nearest home first, newest roles first within each, using city distance when the board gives none', () => {
  assert.deepEqual(selectJobs(listings, jobFilterView(tab), [], '2026-10-19').map(j => j.id), ['trier', 'lux', 'reg-new', 'reg-old']);
  assert.deepEqual(selectJobs(listings, jobFilterView({ ...tab, distance: '50' }), [], '2026-10-19').map(j => j.id), ['trier', 'lux']);
});
test('posted, place, field and role filters combine, and facets count what the other filters leave', () => {
  const pick = extra => selectJobs(listings, jobFilterView({ ...tab, ...extra }), [], '2026-10-19').map(j => j.id).sort();
  assert.deepEqual(pick({ posted: '3' }), ['reg-new', 'trier']);
  assert.deepEqual(pick({ jobCountry: 'Germany' }), ['reg-new', 'reg-old', 'trier']);
  assert.deepEqual(pick({ jobCity: 'Regensburg', group: 'english' }), ['reg-new']);
  assert.deepEqual(pick({ field: 'Analytics & BI', group: 'student' }), ['trier']);
  const facets = jobFacets(listings, { ...tab, jobCountry: 'Germany', field: 'Software engineering' }, [], '2026-10-19');
  assert.deepEqual(facets.countries.map(r => [r.value, r.count]), [['Germany', 2]]);
  assert.deepEqual(facets.fields.map(r => [r.value, r.count]), [['Analytics & BI', 1], ['Software engineering', 2]].sort((a, b) => b[1] - a[1]));
  assert.deepEqual(facets.cities.map(r => r.value), ['Regensburg']);
  assert.equal(facets.groups.find(r => r.value === 'english').count, 1);
  assert.equal(activeJobFilters({ ...tab, posted: '7', hideSenior: true }), 2);
});
test('Jobs tab filters do not leak into the Everything view, and the Jobs tab ignores the shared city filter', () => {
  const data = { date: '2026-10-19', jobs: listings, saved_jobs: [], events: { items: [] } };
  assert.equal(selectExplore(data, { ...initialFilters, posted: '1', jobCity: 'Trier' }).length, 4);
  assert.equal(selectExplore(data, { ...tab, city: 'Trier' }).length, 4);
});
test('job filters are remembered across restarts', () => {
  const store = new Map(), storage = { getItem: key => store.get(key) ?? null, setItem: (key, value) => store.set(key, value) };
  saveJobFilters({ ...tab, posted: '7', jobCity: 'Trier', field: 'Analytics & BI', hideSenior: true, search: 'secret' }, storage);
  assert.deepEqual(savedJobFilters(storage), { posted: '7', group: 'all', jobCountry: 'all', jobCity: 'Trier', field: 'Analytics & BI', source: 'all', sort: 'distance', hideSenior: true });
  assert.deepEqual(savedJobFilters({ getItem: () => '{broken' }), {});
});
