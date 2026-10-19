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
// A story is known by its feed link and, once found, the publisher's direct link.
export const storyKeys = item => [item.url, item.article_url].filter(Boolean);
export const findStory = (items, href) => href ? items.find(item => storyKeys(item).includes(href)) : undefined;
export function isSaved(saved, item) { const keys = new Set(saved.flatMap(storyKeys)); return storyKeys(item).some(key => keys.has(key)); }
// Saved stories outlive the 14-day news window; while a story is still gathered, its live details win.
export const savedStories = (news, saved) => saved.map(row => ({ ...row, ...(findStory(news, row.url) || findStory(news, row.article_url) || {}), saved_at: row.saved_at }));
