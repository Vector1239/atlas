import React, { useEffect, useState } from 'react';
import { ArrowClockwiseIcon, ArrowUpRightIcon, NewspaperIcon, TranslateIcon } from '@phosphor-icons/react';
import { niceDate, safeLink } from './format.js';
import { initialNewsFilters, selectNews, newsRegions } from './news-filters.js';
import './news.css';

const published = value => value && Number.isFinite(Date.parse(value)) ? niceDate(value, { day:'numeric', month:'short', hour:'2-digit', minute:'2-digit' }) : 'Date not provided';
export function ArticleImage({ item, prominent = false }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [item.picture?.url]);
  if (!item.picture || failed) return null;
  // Only the app-owned image endpoint is rendered, never URLs embedded in feed HTML.
  if (!/^\/api\/news\/images\/[a-f0-9]{64}$/.test(item.picture.url)) return null;
  return <figure className="article-picture"><a href={safeLink(item.article_url || item.url)} target="_blank" rel="noreferrer" aria-label={`Read ${item.title_en || item.title}`}><img src={item.picture.url} alt={item.picture.alt || `Article image supplied by ${item.source}`} loading={prominent ? 'eager' : 'lazy'} decoding="async" onError={() => setFailed(true)} /></a><figcaption>{item.picture.credit || item.source} · Article image</figcaption></figure>;
}
function Story({ item, original, ask, prominent = false, compact = false }) {
  return <article className={`news-story ${prominent ? 'prominent' : ''} ${compact ? 'compact' : ''}`}>
    {!compact && !prominent && <ArticleImage item={item} />}
    <div className="story-copy"><div className="story-kicker"><span>{newsRegions[item.ring] || 'From your sources'}</span><span>·</span><span>{item.source.replace('Google News: ', '')}</span></div>
      <h2><a href={safeLink(item.article_url || item.url)} target="_blank" rel="noreferrer">{original ? item.title : item.title_en || item.title}<ArrowUpRightIcon size={16} /></a></h2>
      {!original && item.translation_needed && <span className="untranslated-label">Original headline · English translation pending</span>}
      {prominent && <ArticleImage item={item} prominent />}
      <div className="story-date"><time dateTime={item.published || undefined}>{published(item.published)}</time>{item.feed && item.feed !== item.source && <span>Via {item.feed.replace('Google News: ', 'Google News · ')}</span>}</div>
      {!original && item.translated && <details className="headline-original"><summary>Original headline</summary><p>{item.title}</p></details>}
      <div className="story-actions"><a href={safeLink(item.article_url || item.url)} target="_blank" rel="noreferrer">Read at source <ArrowUpRightIcon size={12} /></a><button onClick={() => ask(`Explain this news item in plain English using only its headline, and say what further information you would need. Do not invent article details.\n${item.title}\n${item.url}`)}>Ask Atlas</button></div>
    </div>
  </article>;
}
export default function News({ data, act, ask }) {
  const [filters, setFilters] = useState(initialNewsFilters), [original, setOriginal] = useState(false), [limit, setLimit] = useState(18);
  const set = (key,value) => { setFilters(previous => ({ ...previous, [key]:value })); setLimit(18); };
  const items = selectNews(data.news, filters);
  const featured = items.find(item => item.picture) || items[0];
  const rest = items.filter(item => item !== featured), aside = rest.slice(0,2), remaining = rest.slice(2,limit-1);
  const pending = data.news.filter(item => item.translation_needed).length;
  const translating = data.translation?.running && data.translation.kind === 'news';
  const pictures = data.news.filter(item => item.picture).length;
  function reset() { setFilters(initialNewsFilters); setLimit(18); }
  return <>
    <div className="page-heading news-heading"><div><div className="eyebrow">YOUR DAILY READING</div><h1>The world, a little closer.</h1><p>From Trier to Europe. Read the headlines, then go straight to the source.</p></div><button className="button secondary" disabled={data.refresh.running} onClick={() => act('/api/refresh', {})}><ArrowClockwiseIcon size={16} />{data.refresh.running ? 'Refreshing…' : 'Refresh news'}</button></div>
    <div className="news-edition"><span><NewspaperIcon size={16} />{data.news.length} stories · {new Set(data.news.map(item => item.source)).size} sources</span><span>{pictures} with article images{data.news_media?.running ? ` · Finding images… ${data.news_media.completed}/${data.news_media.total}` : ''}</span><button className="text-button" aria-pressed={original} onClick={() => setOriginal(!original)}><TranslateIcon size={15} />{original ? 'Show English headlines' : 'Show original headlines'}</button></div>
    <section className="news-filter-panel" aria-label="News filters"><div className="news-filter-top"><div className="tabs" aria-label="News region">{[['all','Everywhere'],['0','Trier'],['1','Region'],['2','Germany'],['3','Europe']].map(([value,label]) => <button key={value} className={filters.region === value ? 'active' : ''} aria-pressed={filters.region === value} onClick={() => set('region',value)}>{label}</button>)}</div><input className="search" aria-label="Search news" placeholder="Search headlines or sources…" value={filters.search} onChange={event => set('search',event.target.value)} /></div>
      <div className="news-filter-fields"><label>Source<select value={filters.source} onChange={event => set('source',event.target.value)}><option value="all">All sources</option>{[...new Set(data.news.map(item => item.source))].sort().map(source => <option key={source}>{source}</option>)}</select></label><label>Published<select value={filters.period} onChange={event => set('period',event.target.value)}><option value="all">All gathered stories</option><option value="24">Past 24 hours</option><option value="72">Past 3 days</option></select></label><label>Order<select value={filters.sort} onChange={event => set('sort',event.target.value)}><option value="local">Local first</option><option value="newest">Newest first</option></select></label><label className="check-label"><input type="checkbox" checked={filters.photos} onChange={event => set('photos',event.target.checked)} />With article images</label><button className="text-button" onClick={reset}>Reset filters</button></div>
    </section>
    {!!pending && <div className="headline-translation news-translation"><div><p>{pending} new {pending === 1 ? 'headline awaits' : 'headlines await'} English translation. {data.model.ready ? 'Translate locally on this Mac.' : 'Qwen is paused; start it in Settings to translate.'}</p></div><button className="button secondary" disabled={!data.model.ready || data.busy} onClick={() => act('/api/news/translate', {})}>{translating ? `Translating… ${data.translation.completed} done` : 'Translate new headlines'}</button></div>}
    {data.translation?.kind === 'news' && data.translation.error && <p className="form-error" role="alert">{data.translation.error}</p>}
    <div className="news-results-label" aria-live="polite"><span>{items.length} {items.length === 1 ? 'story' : 'stories'} in this view</span><span>{original ? 'Original headlines' : 'English where translated'}</span></div>
    {featured && <><section className={`news-lead ${aside.length ? '' : 'single'}`} aria-label="Leading stories"><Story key={featured.url} item={featured} original={original} ask={ask} prominent /><div className="news-side-stories">{aside.map(item => <Story key={item.url} item={item} original={original} ask={ask} compact />)}</div></section>
    {!!remaining.length && <section className="news-more" aria-label="More news"><div className="news-section-heading"><span>KEEP READING</span><h2>Across your sources.</h2></div><div className="news-story-grid">{remaining.map(item => <Story key={item.url} item={item} original={original} ask={ask} />)}</div></section>}
    <div className="news-pagination"><span>Showing {Math.min(limit,items.length)} of {items.length} stories</span>{items.length > limit && <button className="button secondary" onClick={() => setLimit(limit+18)}>Load more stories</button>}</div></>}
    {!items.length && <div className="empty"><NewspaperIcon size={32} /><h3>{data.news.length ? 'No stories match this view.' : 'Your reading starts here.'}</h3><p>{data.news.length ? 'Try another source, region or search.' : 'Refresh news to gather the latest headlines.'}</p><button className="button secondary" onClick={data.news.length ? reset : () => act('/api/refresh', {})} disabled={!data.news.length && data.refresh.running}>{data.news.length ? 'Clear filters' : 'Refresh news'}</button></div>}
    <p className="news-footnote">Images come from the publisher’s feed or article preview and stay linked to that story. Some publishers and Google News links don’t expose an accessible image. Original reporting, pictures and full articles belong to their respective sources.</p>
  </>;
}
