// Shared display helpers for every page.
export const niceDate = (date, options = { day: 'numeric', month: 'short' }) => new Date(date).toLocaleDateString('en-GB', options);
export const safeLink = url => { try { return ['http:', 'https:'].includes(new URL(url).protocol) ? url : '#'; } catch { return '#'; } };
