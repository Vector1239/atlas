import { test } from 'node:test';
import assert from 'node:assert/strict';
import { dateRange, dayLabel, eventFacets, matchesEvent } from '../src/event-filters.js';
import { initialFilters, selectExplore } from '../src/explore-filters.js';
const today = '2026-10-21'; // a Wednesday
const ev = (id, fields) => ({ id, title:id, start:today, end:today, city:'Berlin', country:'Germany', venue:'Arena', category:'Music', genre:'Rock', source:'Ticketmaster', ...fields });
const events = [ev('rock'), ev('jazz', { genre:'Jazz', city:'Hamburg', start:'2026-10-24', end:'2026-10-24' }),
  ev('match', { category:'Sports', genre:'Soccer', city:'Vienna', country:'Austria', start:'2026-10-25', end:'2026-10-25', lineup:['Rapid Wien','Austria Wien'] }),
  ev('fair', { category:'Culture', genre:'', city:'Paris', country:'France', start:'2026-10-15', end:'2026-11-30', description:'Art fair at Grand Palais, Paris.' })];
test('date presets cover today, the coming weekend and rolling windows, including events already running', () => {
  assert.deepEqual(dateRange('weekend', today), ['2026-10-23', '2026-10-25']);
  assert.deepEqual(dateRange('weekend', '2026-10-24'), ['2026-10-24', '2026-10-25']);
  assert.deepEqual(dateRange('weekend', '2026-10-25'), ['2026-10-25', '2026-10-25']);
  assert.deepEqual(dateRange('7', today), [today, '2026-10-27']);
  const pick = when => events.filter(e => matchesEvent(e, { ...initialFilters, when }, today)).map(e => e.id);
  assert.deepEqual(pick('today'), ['rock', 'fair']);
  assert.deepEqual(pick('weekend'), ['jazz', 'match', 'fair']);
});
test('facets count what the other filters leave and search reaches line-ups and descriptions', () => {
  const filters = { ...initialFilters, country:'Germany' };
  const facets = eventFacets(events, filters, today);
  assert.deepEqual(facets.countries.map(r => [r.value, r.count]), [['Germany', 2], ['Austria', 1], ['France', 1]]);
  assert.deepEqual(facets.cities.map(r => r.value), ['Berlin', 'Hamburg']);
  assert.deepEqual(facets.categories.map(r => [r.value, r.count]), [['Music', 2]]);
  assert.deepEqual(eventFacets(events, { ...initialFilters, category:'Music' }, today).genres.map(r => r.value), ['Jazz', 'Rock']);
  assert.deepEqual(selectExplore({ date:today, jobs:[], events:{ items:events } }, { ...initialFilters, kind:'events', search:'rapid' }).map(e => e.id), ['match']);
  assert.deepEqual(selectExplore({ date:today, jobs:[], events:{ items:events } }, { ...initialFilters, kind:'events', search:'grand palais' }).map(e => e.id), ['fair']);
  assert.deepEqual(selectExplore({ date:today, jobs:[], events:{ items:events } }, { ...initialFilters, kind:'events', category:'Music', genre:'Jazz' }).map(e => e.id), ['jazz']);
});
test('day headings name today, tomorrow and events already on', () => {
  assert.equal(dayLabel(events[0], today), 'Today');
  assert.equal(dayLabel(ev('x', { start:'2026-10-22' }), today), 'Tomorrow');
  assert.equal(dayLabel(events[3], today), 'On now');
  assert.equal(dayLabel(events[1], today), 'Saturday 24 October');
});
test('nearest home is the default order: whole cities by distance, each city in date order', () => {
  const trier = { lat:49.7557, lon:6.6394 }, venue = { lat:49.7601, lon:6.6447 }, lux = { lat:49.61, lon:6.13 };
  const items = [ev('t-city-nov', { city:'Trier', start:'2026-11-05', end:'2026-11-05', location:trier }), ev('lux', { city:'Luxembourg', country:'Luxembourg', start:'2026-10-21', end:'2026-10-21', location:lux }),
    ev('t-venue-oct', { city:'Trier', start:'2026-10-21', end:'2026-10-21', location:venue }), ev('t-city-oct', { city:'Trier', start:'2026-10-22', end:'2026-10-22', location:trier })];
  assert.equal(initialFilters.eventSort, 'nearest');
  assert.deepEqual(selectExplore({ date:today, jobs:[], events:{ items } }, { ...initialFilters, kind:'events' }).map(e => e.id), ['t-venue-oct', 't-city-oct', 't-city-nov', 'lux']);
  assert.deepEqual(selectExplore({ date:today, jobs:[], events:{ items } }, { ...initialFilters, kind:'events', eventSort:'soonest' }).map(e => e.id), ['lux', 't-venue-oct', 't-city-oct', 't-city-nov']);
});
test('event filters are remembered between visits and bad or missing storage is ignored', async () => {
  const { savedEventFilters, saveEventFilters } = await import('../src/event-filters.js');
  const store = new Map(), storage = { getItem: key => store.get(key) ?? null, setItem: (key, value) => store.set(key, value) };
  saveEventFilters({ ...initialFilters, kind:'events', when:'weekend', category:'Music', genre:'Jazz', country:'Germany', city:'Berlin', search:'not kept' }, storage);
  assert.deepEqual(savedEventFilters(storage), { kind:'events', when:'weekend', category:'Music', genre:'Jazz', country:'Germany', city:'Berlin', eventSort:'nearest' });
  store.set('atlas.explore.events', '{broken');
  assert.deepEqual(savedEventFilters(storage), {});
  assert.deepEqual(savedEventFilters({ getItem: () => { throw Error('blocked'); } }), {});
  assert.doesNotThrow(() => saveEventFilters(initialFilters, undefined));
});
