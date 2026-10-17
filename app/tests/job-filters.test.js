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
