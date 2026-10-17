import React, { useState } from 'react';
import { ArrowUpRightIcon, TranslateIcon } from '@phosphor-icons/react';
import { safeLink } from './format.js';

export default function Headlines({ data, act, ask }) {
  const [original, setOriginal] = useState(false), [expanded, setExpanded] = useState(false);
  const pending = data.news.filter(item => item.translation_needed).length;
  const translating = data.translation?.running && data.translation.kind === 'news';
  const items = expanded ? data.news : data.news.slice(0, 7);
  return <section className="card headlines"><div className="card-heading"><div><div className="eyebrow">TRIER & BEYOND</div><h2>Around you</h2></div><button className="text-button" aria-pressed={original} onClick={() => setOriginal(!original)}><TranslateIcon size={16} />{original ? 'Show English' : 'Show originals'}</button></div>
    {!!pending && <div className="headline-translation"><p>{pending} new headlines await English translation. {data.model.ready ? 'Translate with local Qwen.' : 'Qwen is paused. Start it in Settings when you want to translate new headlines.'}</p><button className="text-button" disabled={!data.model.ready || data.busy} onClick={() => act('/api/news/translate', {})}>{translating ? `Translating… ${data.translation.completed} done` : 'Translate new headlines'}</button></div>}
    {data.translation?.kind === 'news' && data.translation.error && <p className="form-error" role="alert">{data.translation.error}</p>}
    {!items.length && <p className="event-context">Headlines will appear after your sources refresh.</p>}
    <div className="news-list">{items.map((item, index) => <article key={item.url} className="news-item"><span className="news-number">{String(index + 1).padStart(2, '0')}</span><div><div className="news-meta">{['Trier', 'Region', 'Germany', 'Europe'][item.ring]}<span>·</span>{item.source.replace('Google News: ', '')}</div><a href={safeLink(item.url)} target="_blank" rel="noreferrer">{original ? item.title : item.title_en || item.title}<ArrowUpRightIcon size={14} /></a>{!original && item.translation_needed && <small className="untranslated-label">Original headline · translation pending</small>}{!original && item.translated && <details className="headline-original"><summary>Original headline</summary><p>{item.title}</p></details>}<button className="subtle-button" onClick={() => ask(`Explain this news item in plain English using only its headline, and say what further information you would need. Do not invent article details.\n${item.title}\n${item.url}`)}>Ask Atlas about this</button></div></article>)}</div>
    {data.news.length > 7 && <button className="text-button full-link" onClick={() => setExpanded(!expanded)}>{expanded ? 'Show fewer headlines' : `Browse all ${data.news.length} headlines`}</button>}
  </section>;
}
