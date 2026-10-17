import React, { useEffect, useRef, useState } from 'react';
import { ArrowClockwiseIcon, ArrowUpRightIcon, NewspaperIcon, SlidersHorizontalIcon, TranslateIcon, XIcon } from '@phosphor-icons/react';
import { niceDate, safeLink } from './format.js';
import { initialNewsFilters, selectNews, newsRegions } from './news-filters.js';
import './news.css';

const published = value => value && Number.isFinite(Date.parse(value)) ? niceDate(value, { day:'numeric', month:'short', hour:'2-digit', minute:'2-digit' }) : 'Date not provided';
export function ArticleImage({ item, prominent = false, placeholder = false }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [item.picture?.url]);
  // Only the app-owned image endpoint is rendered, never URLs embedded in feed HTML.
  const available = !failed && /^\/api\/news\/images\/[a-f0-9]{64}$/.test(item.picture?.url || '');
  if (!available) return placeholder ? <div className="story-image-unavailable"><NewspaperIcon size={27} weight="light" aria-hidden="true" /><span>No publisher image</span></div> : null;
  return <figure className="article-picture"><a href={safeLink(item.article_url || item.url)} target="_blank" rel="noreferrer" aria-label={`Read ${item.title_en || item.title}`}><img src={item.picture.url} alt={item.picture.alt || `Article image supplied by ${item.source}`} loading={prominent ? 'eager' : 'lazy'} decoding="async" onError={() => setFailed(true)} /></a><figcaption>{item.picture.credit || item.source} · Article image</figcaption></figure>;
}
function Story({ item, original, ask, prominent }) {
  return <article className="news-story">
    <ArticleImage item={item} prominent={prominent} placeholder />
    <div className="story-copy"><div className="story-kicker"><span>{newsRegions[item.ring] || 'From your sources'}</span><span>·</span><span>{item.source.replace('Google News: ', '')}</span></div>
      <h2><a href={safeLink(item.article_url || item.url)} target="_blank" rel="noreferrer">{original ? item.title : item.title_en || item.title}</a></h2>
      {!original && item.translation_needed && <span className="untranslated-label">Original headline · English translation pending</span>}
      <div className="story-date"><time dateTime={item.published || undefined}>{published(item.published)}</time>{item.feed && item.feed !== item.source && <span>Via {item.feed.replace('Google News: ', 'Google News · ')}</span>}</div>
      {!original && item.translated && <details className="headline-original"><summary>Original headline</summary><p>{item.title}</p></details>}
      <div className="story-actions"><a href={safeLink(item.article_url || item.url)} target="_blank" rel="noreferrer">Read at source <ArrowUpRightIcon size={12} /></a><button onClick={() => ask(`Explain this news item in plain English using only its headline, and say what further information you would need. Do not invent article details.\n${item.title}\n${item.url}`)}>Ask Atlas</button></div>
    </div>
  </article>;
}
export default function News({ data, act, ask }) {
  const [filters, setFilters] = useState(initialNewsFilters), [original, setOriginal] = useState(false), [panelOpen, setPanelOpen] = useState(false);
  const panel = useRef(null);
  const set = (key,value) => setFilters(previous => ({ ...previous, [key]:value }));
  const items = selectNews(data.news, filters);
  const activeFilters = Object.keys(initialNewsFilters).filter(key => filters[key] !== initialNewsFilters[key]).length;
  const pending = data.news.filter(item => item.translation_needed).length;
  const translating = data.translation?.running && data.translation.kind === 'news';
  const pictures = data.news.filter(item => item.picture).length;
  const reset = () => setFilters(initialNewsFilters);
  const openPanel = () => { if (!panel.current.open) panel.current.showModal(); setPanelOpen(true); };
  const closePanel = () => { panel.current?.close(); setPanelOpen(false); };
  return <>
    <header className="news-toolbar"><div className="news-title"><h1>News.</h1><span aria-live="polite">{activeFilters ? `${items.length} of ${data.news.length}` : data.news.length} stories</span></div><div className="news-toolbar-actions">
      {!!activeFilters && <button className="text-button news-clear" onClick={reset}>Clear filters</button>}
      <button className="button secondary" aria-haspopup="dialog" aria-expanded={panelOpen} aria-controls="news-options" onClick={openPanel}><SlidersHorizontalIcon size={16} />Filters & display{!!activeFilters && <span className="news-filter-count">{activeFilters}</span>}</button>
      <button className="button secondary" disabled={data.refresh.running} onClick={() => act('/api/refresh', {})} aria-label="Refresh news"><ArrowClockwiseIcon size={16} /><span>{data.refresh.running ? 'Refreshing…' : 'Refresh'}</span></button>
    </div></header>
    {!original && !!pending && <div className="news-translation-status" role="status"><TranslateIcon size={14} /><span>{translating ? `Translating headlines locally · ${pending} remaining` : data.model.ready ? `${pending} headlines queued · English translations run automatically while Gemma is idle` : `${pending} headlines await English translation · Start Gemma in Settings`}</span>{data.model.ready && !translating && <button className="text-button" disabled={data.busy || data.translation.running} onClick={() => act('/api/news/translate', {})}>Translate now</button>}</div>}
    {!!activeFilters && <div className="news-view-summary">{filters.region !== 'all' ? newsRegions[Number(filters.region)] : 'Everywhere'} · {filters.source !== 'all' ? filters.source : 'All sources'}{filters.search && ` · “${filters.search}”`}{filters.period !== 'all' && ` · Past ${filters.period} hours`}{filters.photos && ' · With images'}{filters.sort === 'newest' && ' · Newest first'}</div>}
    {!!items.length && <section className="news-story-grid" aria-label="News stories">{items.map((item,index) => <Story key={item.url} item={item} original={original} ask={ask} prominent={index < 3} />)}</section>}
    {!items.length && <div className="empty"><NewspaperIcon size={32} /><h3>{data.news.length ? 'No stories match this view.' : 'Your reading starts here.'}</h3><p>{data.news.length ? 'Try another source, region or search.' : 'Refresh news to gather the latest headlines.'}</p><button className="button secondary" onClick={data.news.length ? reset : () => act('/api/refresh', {})} disabled={!data.news.length && data.refresh.running}>{data.news.length ? 'Clear filters' : 'Refresh news'}</button></div>}
    <p className="news-footnote">All {items.length} {items.length === 1 ? 'story' : 'stories'} shown. Gathered stories stay available for 14 days, even after leaving a publisher’s feed. Images and reporting belong to their publishers; stories without an accessible publisher image are labelled.</p>
    <dialog ref={panel} id="news-options" className="news-drawer" aria-labelledby="news-options-title" onClose={() => { if (!panel.current.open) setPanelOpen(false); }} onClick={event => { if (event.target === event.currentTarget) closePanel(); }}>
      <div className="news-drawer-inner"><header className="news-drawer-heading"><div><h2 id="news-options-title">Your news view</h2><p>{data.news.length} stories from {new Set(data.news.map(item => item.source)).size} sources</p></div><button type="button" className="icon-button" aria-label="Close news filters" onClick={closePanel}><XIcon size={20} /></button></header>
        <div className="news-drawer-body"><section aria-label="News filters" className="news-drawer-section">
          <label>Search<input autoFocus aria-label="Search news" placeholder="Headlines or sources…" value={filters.search} onChange={event => set('search',event.target.value)} /></label>
          <label>Region<select value={filters.region} onChange={event => set('region',event.target.value)}>{[['all','Everywhere'],['0','Trier'],['1','Region'],['2','Germany'],['3','Europe']].map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label>Source<select value={filters.source} onChange={event => set('source',event.target.value)}><option value="all">All sources</option>{[...new Set(data.news.map(item => item.source))].sort().map(source => <option key={source}>{source}</option>)}</select></label>
          <label>Published<select value={filters.period} onChange={event => set('period',event.target.value)}><option value="all">All gathered stories</option><option value="24">Past 24 hours</option><option value="72">Past 3 days</option></select></label>
          <label>Order<select value={filters.sort} onChange={event => set('sort',event.target.value)}><option value="local">Local first</option><option value="newest">Newest first</option></select></label>
          <label className="news-checkbox"><input type="checkbox" checked={filters.photos} onChange={event => set('photos',event.target.checked)} />Only stories with article images</label>
        </section><section className="news-drawer-section" aria-label="Headline display"><h3>Headlines & images</h3>
          <button className="text-button news-language" aria-pressed={original} onClick={() => setOriginal(!original)}><TranslateIcon size={16} />{original ? 'Show English headlines' : 'Show original headlines'}</button>
          <p>{original ? 'Showing the publisher’s original headlines.' : 'Showing English translations where available.'}</p>
          {!!pending && <div className="news-translation"><p>{pending} {pending === 1 ? 'headline awaits' : 'headlines await'} translation. {data.model.ready ? 'Translate locally on this Mac.' : 'Start Gemma in Settings to translate.'}</p><button className="button secondary" disabled={!data.model.ready || data.busy || data.translation.running} onClick={() => act('/api/news/translate', {})}>{translating ? `Translating… ${data.translation.completed} done` : 'Translate new headlines'}</button></div>}
          {data.translation?.kind === 'news' && data.translation.error && <p className="form-error" role="alert">{data.translation.error}</p>}
          <p>{pictures} stories have publisher images.{data.news_media?.running ? ` Finding images… ${data.news_media.completed}/${data.news_media.total}.` : ''} All stories appear by default, including those without an image.</p>
        </section></div>
        <footer className="news-drawer-footer"><button className="text-button" onClick={reset}>Reset filters</button><button className="button" onClick={closePanel}>Show {items.length} {items.length === 1 ? 'story' : 'stories'}</button></footer>
      </div>
    </dialog>
  </>;
}
