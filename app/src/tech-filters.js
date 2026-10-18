import { validLocation } from './explore-filters.js';

export const initialTechFilters = { kind:'all', search:'', area:'all', distance:'any', city:'all', period:'all', source:'all', sort:'nearest' };
export function distanceFrom(location, base) {
  if (!validLocation(location) || !validLocation(base)) return null;
  const rad = v => v * Math.PI / 180;
  const a = Math.sin(rad(location.lat - base.lat) / 2) ** 2 + Math.cos(rad(base.lat)) * Math.cos(rad(location.lat)) * Math.sin(rad(location.lon - base.lon) / 2) ** 2;
  return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(Math.max(0, 1 - a)));
}
export function selectTech(tech, filters, home, today) {
  const cutoff = new Date(`${today}T00:00:00Z`); cutoff.setUTCDate(cutoff.getUTCDate() + Number(filters.period));
  return (tech.events || []).map(item => ({ ...item, distance: item.online ? null : distanceFrom(item.location, home) })).filter(item =>
    (item.end || item.start) >= today && (filters.kind === 'all' || filters.kind === item.kind)
    && `${item.title} ${item.city} ${item.country} ${item.source} ${item.description || ''} ${(item.topics || []).join(' ')} ${item.organizer || ''} ${(item.listed_by || []).map(s => s.name).join(' ')}`.toLowerCase().includes(filters.search.trim().toLowerCase())
    && (!filters.source || filters.source === 'all' || item.source === filters.source || (item.listed_by || []).some(s => s.name === filters.source))
    && (filters.area === 'all' || (filters.area === 'online' ? item.online : filters.area === 'germany' ? !item.online && item.country === 'Germany' : !item.online))
    && (filters.distance === 'any' || item.distance !== null && item.distance <= Number(filters.distance))
    && (filters.city === 'all' || item.city === filters.city)
    && (filters.period === 'all' || item.start <= cutoff.toISOString().slice(0,10)))
    .sort((a,b) => (filters.sort === 'nearest' ? (a.distance ?? Infinity) - (b.distance ?? Infinity) : 0) || a.start.localeCompare(b.start) || a.title.localeCompare(b.title));
}

const normalized = value => String(value || '').trim().replace(/\s+/g, ' ').toLowerCase();

// Group only the filtered occurrences, so each card's next date matches the view.
export function groupTechEvents(events) {
  const groups = new Map();
  for (const event of events) {
    const identity = event.series_id || event.url;
    const key = identity && event.source && event.title
      ? JSON.stringify([identity, ...[event.source, event.series_id ? 'series' : 'listing',
        event.kind, event.title, event.city, event.country, event.venue,
        event.organizer, event.online ? 'online' : 'in person'].map(normalized)])
      : `individual:${event.id || groups.size}`;
    if (!groups.has(key)) groups.set(key, { ...event, id:key, occurrences:[] });
    const group = groups.get(key);
    if (!group.occurrences.some(item => item.start === event.start && item.end === event.end
      && item.starts_at === event.starts_at && item.ends_at === event.ends_at
      && item.time_note === event.time_note)) group.occurrences.push(event);
  }
  return [...groups.values()].map(group => {
    const occurrences = group.occurrences.sort((a,b) => a.start.localeCompare(b.start)
      || (a.starts_at || a.time_note || '').localeCompare(b.starts_at || b.time_note || ''));
    return { ...occurrences[0], id:group.id, occurrences };
  });
}
