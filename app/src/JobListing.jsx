import React, { useState } from 'react';
import { ArrowUpRightIcon, BookmarkSimpleIcon, CaretDownIcon, MapPinIcon, SparkleIcon, ThumbsUpIcon, ThumbsDownIcon } from '@phosphor-icons/react';
import { distanceLabel } from './job-filters.js';
import { niceDate, safeLink as link } from './format.js';
const date = value => value ? niceDate(value) : 'Date not provided';

export function JobListing({ job, original = false, data, act, ask }) {
  const [loading, setLoading] = useState(false), [detailError, setDetailError] = useState('');
  async function readDetails() {
    if (job.text || loading) return;
    setLoading(true);
    try {
      const result = await act('/api/jobs/details', { id: job.id });
      setDetailError(result?.detail_error || (!result ? 'Could not load details. Try again or open the original listing.' : ''));
    } finally { setLoading(false); }
  }
  return <article className="job-listing">
      <div className="job-listing-main"><div className="job-employer"><span className="company-mark">{(job.company || '?')[0]}</span><span>{job.company || 'Employer not provided'}</span></div><h2><a href={link(job.url)} target="_blank" rel="noreferrer">{original ? job.title : job.title_en || job.title}</a></h2>{job.translation_needed && !original && <span className="untranslated-label">Original title · English translation pending</span>}<div className="job-labels">{job.flags.includes('student-job') && <span className="badge sage">Student role</span>}{job.flags.includes('senior') && <span className="badge">Senior / leadership</span>}{job.remote && <span className="badge sage">{job.remote_scope ? `Remote · ${job.remote_scope}` : 'Remote mentioned'}</span>}{job.flags.includes('english') && <span className="badge">English posting detected</span>}{job.flags.includes('german-required') && <span className="badge rose">German required</span>}</div></div>
      <div className="job-place"><MapPinIcon size={18} weight="bold" /><div><strong>{job.city}</strong><span>{job.region_name || 'Region not provided'}</span><small>{distanceLabel(job)}</small></div></div>
      <div className="job-provenance"><span className="eyebrow">JOB BOARD</span><a href={link(job.url)} target="_blank" rel="noreferrer">{job.source_label}<ArrowUpRightIcon size={13} weight="bold" /></a><small>Posted {date(job.posted)}</small>{job.via && <small>Publisher: {job.via}</small>}</div>
      <button className={`icon-button job-bookmark ${data.saved_jobs.includes(job.id) ? 'is-saved' : ''}`} aria-label={`${data.saved_jobs.includes(job.id) ? 'Unsave' : 'Save'} ${job.title_en || job.title}`} onClick={() => act('/api/jobs/save', { id: job.id })}><BookmarkSimpleIcon size={21} weight={data.saved_jobs.includes(job.id) ? 'fill' : 'bold'} /></button>
      <details className="job-details" onToggle={event => { if (event.currentTarget.open) readDetails(); }}><summary>Original title & details<CaretDownIcon size={13} weight="bold" /></summary><div><p className="original-title">{job.title}</p>{job.text ? <><p className="job-description">{job.text}</p>{job.detail_source && <small>Details from {job.detail_source}</small>}</> : <p role="status">{loading ? 'Reading the source’s job description…' : detailError || 'Open these details to read the source’s job description.'}</p>}<div className="job-detail-actions"><a className="text-button" href={link(job.url)} target="_blank" rel="noreferrer">Open original listing<ArrowUpRightIcon size={14} /></a><button className="text-button" disabled={data.busy || loading} onClick={() => ask(`In English, assess this job against my profile. Separate confirmed details from unknown requirements. Do not infer English eligibility from a translated title.\n${JSON.stringify(job)}`)}><SparkleIcon size={14} />Ask Atlas about fit</button><div className="ratings"><button className={`icon-button ${data.feedback[job.id]?.rating === 'up' ? 'liked' : ''}`} aria-label={`Like ${job.title_en || job.title}`} onClick={() => act('/api/jobs/rate', { id: job.id, rating: 'up' }, 'Feedback saved.')}><ThumbsUpIcon size={16} weight="bold" /></button><button className={`icon-button ${data.feedback[job.id]?.rating === 'down' ? 'disliked' : ''}`} aria-label={`Dislike ${job.title_en || job.title}`} onClick={() => act('/api/jobs/rate', { id: job.id, rating: 'down' }, 'Feedback saved.')}><ThumbsDownIcon size={16} weight="bold" /></button></div></div></div></details>
    </article>;
}
