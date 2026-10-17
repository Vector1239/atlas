import React from 'react';
import { ArrowUpRightIcon } from '@phosphor-icons/react';
import { safeLink } from './format.js';
import { newsRegions } from './news-filters.js';

export default function Headlines({ data, openNews }) {
  return <section className="card headlines"><div className="card-heading"><div><div className="eyebrow">TRIER & BEYOND</div><h2>Around you</h2></div><button className="text-button" onClick={openNews}>Open News <ArrowUpRightIcon size={14} /></button></div>
    {!data.news.length && <p className="event-context">Headlines will appear after your sources refresh.</p>}
    <div className="news-list">{data.news.slice(0,3).map((item,index) => <article key={item.url} className="news-item"><span className="news-number">{String(index+1).padStart(2,'0')}</span><div><div className="news-meta">{newsRegions[item.ring]}<span>·</span>{item.source.replace('Google News: ','')}</div><a href={safeLink(item.url)} target="_blank" rel="noreferrer">{item.title_en || item.title}<ArrowUpRightIcon size={14} /></a>{item.translation_needed && <small className="untranslated-label">Original headline · English translation pending</small>}</div></article>)}</div>
    {!!data.news.length && <button className="text-button full-link" onClick={openNews}>Browse all {data.news.length} stories <ArrowUpRightIcon size={14} /></button>}
  </section>;
}
