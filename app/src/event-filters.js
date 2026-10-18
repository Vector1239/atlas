// Event-only filters for the Events tab: dates, place, type and genre, each with live counts.
export const whenOptions = [['any', 'Any date'], ['today', 'Today'], ['weekend', 'This weekend'], ['7', 'Next 7 days'], ['30', 'Next 30 days']];
export const eventSorts = [['soonest', 'Soonest first'], ['nearest', 'Nearest home first']];

const day = value => new Date(`${value}T12:00:00`);
const iso = date => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
const shift = (value, days) => { const date = day(value); date.setDate(date.getDate() + days); return iso(date); };

export function dateRange(when, today) {
  if (!when || when === 'any') return null;
  if (when === 'today') return [today, today];
  if (when === 'weekend') {
    const weekday = day(today).getDay(); // Friday to Sunday; on a weekend, the rest of it
    if (weekday === 0) return [today, today];
    if (weekday >= 5) return [today, shift(today, 7 - weekday)];
    return [shift(today, 5 - weekday), shift(today, 7 - weekday)];
  }
  return [today, shift(today, Number(when) - 1)];
}

export const eventText = event => [event.title, event.city, event.country, event.venue, event.category, event.genre, event.subgenre, ...(event.lineup || []), event.description, event.source].filter(Boolean).join(' ').toLowerCase();

export function matchesEvent(event, filters, today, skip = '') {
  const range = dateRange(filters.when, today), search = (filters.search || '').trim().toLowerCase();
  return (!search || eventText(event).includes(search))
    && (!range || event.start <= range[1] && (event.end || event.start) >= range[0])
    && (skip === 'category' || filters.category === 'all' || event.category === filters.category)
    && (skip === 'genre' || skip === 'category' || !filters.genre || filters.genre === 'all' || event.genre === filters.genre)
    && (skip === 'country' || !filters.country || filters.country === 'all' || event.country === filters.country)
    && (skip === 'city' || skip === 'country' || filters.city === 'all' || event.city === filters.city);
}

const tally = (rows, key) => {
  const counts = new Map();
  for (const row of rows) if (row[key]) counts.set(row[key], (counts.get(row[key]) || 0) + 1);
  return [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([value, count]) => ({ value, count }));
};

// Each facet counts what the other active filters leave, so a choice never leads to zero results.
export function eventFacets(events, filters, today) {
  const without = skip => events.filter(event => matchesEvent(event, filters, today, skip));
  const inCategory = without('genre').filter(event => filters.category === 'all' || event.category === filters.category);
  const inCountry = without('city').filter(event => !filters.country || filters.country === 'all' || event.country === filters.country);
  return { categories: tally(without('category'), 'category'), genres: tally(inCategory, 'genre'),
    countries: tally(without('country'), 'country'), cities: tally(inCountry, 'city') };
}

export function dayLabel(event, today) {
  if (event.start < today) return 'On now';
  if (event.start === today) return 'Today';
  if (event.start === shift(today, 1)) return 'Tomorrow';
  return day(event.start).toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' });
}

export const activeEventFilters = filters => ['when', 'category', 'genre', 'country', 'city'].filter(key => filters[key] && !['all', 'any'].includes(filters[key])).length;
