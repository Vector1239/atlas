import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseWeather, upcomingEvents, pickJobs } from '../src/today-data.js';
import { skyFor, phaseFor, paletteFor, rng, seedFrom } from '../src/painting.js';

test('weather lines from the Open-Meteo script are read into parts', () => {
  assert.deepEqual(parseWeather('today: light rain, 6–11 °C, rain chance 80%, wind up to 22 km/h'), { label: 'today', condition: 'light rain', low: 6, high: 11, rain: 80, wind: 22 });
  assert.equal(parseWeather('today: -3–2 °C')?.low, undefined);
  assert.equal(parseWeather('')?.condition, undefined);
  assert.equal(parseWeather('tomorrow: snow, -4–-1 °C, rain chance 60%, wind up to 9 km/h').high, -1);
});

test('upcoming events include running ones, put Trier first and skip past or far ones', () => {
  const items = [
    { id: 'far', start: '2026-12-01', area: 'Trier' },
    { id: 'past', start: '2026-10-01', end: '2026-11-01', area: 'Trier' },
    { id: 'running', start: '2026-10-29', end: '2026-11-21', area: 'Region' },
    { id: 'soon', start: '2026-11-08', area: 'Trier' },
  ];
  assert.deepEqual(upcomingEvents(items, '2026-11-05').map(e => e.id), ['soon', 'running']);
});

test('student roles come first, then the nearest', () => {
  const jobs = [{ id: 'a', flags: [], distance_km: 1 }, { id: 'b', flags: ['student-job'], distance_km: 40 }, { id: 'c', flags: ['student-job'], distance_km: 3 }];
  assert.deepEqual(pickJobs(jobs).map(j => j.id), ['c', 'b', 'a']);
});

test('the painting follows the weather and the time of day', () => {
  assert.equal(skyFor('light rain'), 'rain');
  assert.equal(skyFor('rain showers'), 'rain');
  assert.equal(skyFor('thunderstorm with hail'), 'storm');
  assert.equal(skyFor('freezing fog'), 'fog');
  assert.equal(skyFor('mainly clear'), 'clear');
  assert.equal(skyFor('partly cloudy'), 'cloudy');
  assert.equal(phaseFor(7), 'dawn');
  assert.equal(phaseFor(12), 'day');
  assert.equal(phaseFor(17), 'dusk');
  assert.equal(phaseFor(23), 'night');
  assert.equal(paletteFor('night', 'rain').ink, 'light');
  assert.notEqual(paletteFor('day', 'rain'), paletteFor('day', 'clear'));
});

test('the same day paints the same picture', () => {
  const a = rng(seedFrom('2026-11-05-Trier')), b = rng(seedFrom('2026-11-05-Trier')), c = rng(seedFrom('2026-11-06-Trier'));
  const first = [a(), a(), a()];
  assert.deepEqual(first, [b(), b(), b()]);
  assert.notDeepEqual(first, [c(), c(), c()]);
});
