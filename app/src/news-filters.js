export const newsRegions = ['Trier', 'Region', 'Germany', 'Europe'];
export const initialNewsFilters = { search:'', region:'all', source:'all', period:'all', photos:false, sort:'local' };
export function selectNews(items, filters, now = Date.now()) {
  const cutoff = filters.period === 'all' ? -Infinity : now - Number(filters.period) * 3600000;
  return items.filter(item => `${item.title} ${item.title_en || ''} ${item.source} ${item.feed || ''}`.toLowerCase().includes(filters.search.trim().toLowerCase())
    && (filters.region === 'all' || item.ring === Number(filters.region))
    && (filters.source === 'all' || item.source === filters.source)
    && (filters.period === 'all' || Number.isFinite(Date.parse(item.published)) && Date.parse(item.published) >= cutoff)
    && (!filters.photos || !!item.picture))
    .sort((a,b) => (filters.sort === 'local' ? a.ring - b.ring : 0) || (Date.parse(b.published) || 0) - (Date.parse(a.published) || 0) || a.title.localeCompare(b.title));
}
