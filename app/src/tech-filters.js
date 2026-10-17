import { validLocation } from './explore-filters.js';

export const initialTechFilters = { kind:'all', search:'', area:'all', distance:'any', city:'all', period:'all', sort:'nearest' };
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
    && `${item.title} ${item.city} ${item.country} ${item.source} ${item.description || ''}`.toLowerCase().includes(filters.search.trim().toLowerCase())
    && (filters.area === 'all' || (filters.area === 'online' ? item.online : filters.area === 'germany' ? !item.online && item.country === 'Germany' : !item.online))
    && (filters.distance === 'any' || item.distance !== null && item.distance <= Number(filters.distance))
    && (filters.city === 'all' || item.city === filters.city)
    && (filters.period === 'all' || item.start <= cutoff.toISOString().slice(0,10)))
    .sort((a,b) => (filters.sort === 'nearest' ? (a.distance ?? Infinity) - (b.distance ?? Infinity) : 0) || a.start.localeCompare(b.start) || a.title.localeCompare(b.title));
}
