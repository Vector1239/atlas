import React, { useEffect, useRef, useState } from 'react';
import { ArrowClockwiseIcon, ArrowRightIcon, ArrowUpIcon, ArrowUpRightIcon, BookmarkSimpleIcon, BriefcaseIcon, CalendarBlankIcon, ChatCircleDotsIcon, ClockIcon, CloudFogIcon, CloudIcon, CloudLightningIcon, CloudRainIcon, CloudSnowIcon, CloudSunIcon, CodeIcon, EnvelopeSimpleIcon, ForkKnifeIcon, MoonStarsIcon, NewspaperIcon, PauseIcon, PlusIcon, SparkleIcon, SunIcon, TicketIcon } from '@phosphor-icons/react';
import Markdown from './Markdown.jsx';
import Mensa from './Mensa.jsx';
import { distanceLabel } from './job-filters.js';
import { niceDate, safeLink } from './format.js';
import { newsRegions } from './news-filters.js';
import { paint, phaseFor, seedFrom, skyFor } from './painting.js';
import { dayDiff, parseWeather, pickJobs, upcomingEvents } from './today-data.js';
import './today.css';

const when = date => date ? niceDate(date, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '';

const distanceText = job => { const label = distanceLabel(job); return label === 'Distance not provided' ? null : label.replace(' · board reported', ''); };

function WeatherIcon({ sky, night, ...props }) {
  const Component = { storm: CloudLightningIcon, snow: CloudSnowIcon, rain: CloudRainIcon, fog: CloudFogIcon, overcast: CloudIcon, cloudy: night ? CloudIcon : CloudSunIcon, clear: night ? MoonStarsIcon : SunIcon }[sky] || CloudIcon;
  return <Component aria-hidden="true" {...props} />;
}

function Painting({ seed, hour, condition, onPainted }) {
  const canvas = useRef(null);
  useEffect(() => {
    const element = canvas.current;
    if (!element) return undefined;
    let frame = 0, width = 0;
    const draw = () => {
      if (element.clientWidth === width) return;
      width = element.clientWidth;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => { const result = paint(element, { seed, hour, condition }); if (result) onPainted?.(result); });
    };
    draw();
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(draw);
    observer?.observe(element);
    return () => { observer?.disconnect(); cancelAnimationFrame(frame); };
  }, [seed, hour, condition]);
  return <canvas ref={canvas} className="hero-painting" aria-hidden="true" />;
}

function Tile({ icon: Component, title, action, onAction, className = '', children }) {
  return <section className={`tile ${className}`}>
    <header className="tile-head"><h2><Component size={16} weight="bold" aria-hidden="true" />{title}</h2>{action && <button className="tile-link" onClick={onAction}>{action}<ArrowRightIcon size={13} weight="bold" aria-hidden="true" /></button>}</header>
    {children}
  </section>;
}

function Glance({ label, value, detail, onClick, tone = '', progress }) {
  return <button className={`glance ${tone}`} onClick={onClick}>
    <span className="glance-label">{label}</span>
    <strong className="glance-value">{value}</strong>
    {progress != null && <span className="glance-bar"><span style={{ width: `${Math.max(0, Math.min(100, progress))}%` }} /></span>}
    <span className="glance-detail">{detail}</span>
  </button>;
}

function DateChip({ date }) {
  return <span className="date-chip"><span>{niceDate(date, { month: 'short' })}</span><strong>{new Date(date).getDate()}</strong></span>;
}

export default function Today({ data, act, ask, navigate, setModal, stopModel, stoppingModel, saveLink, openSaved }) {
  const [clock, setClock] = useState(() => new Date()), [question, setQuestion] = useState(''), [ink, setInk] = useState('dark');
  useEffect(() => { const timer = setInterval(() => setClock(new Date()), 5 * 60000); return () => clearInterval(timer); }, []);
  const hour = clock.getHours(), today = data.date;
  const weather = parseWeather((data.weather || []).find(line => line.startsWith('today:'))), tomorrow = parseWeather((data.weather || []).find(line => line.startsWith('tomorrow:')));
  const sky = skyFor(weather?.condition), night = phaseFor(hour) === 'night';
  const greeting = hour < 5 ? 'Good night' : hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';

  const deadlines = (data.deadlines || []).filter(d => d.days_left >= -3).sort((a, b) => a.days_left - b.days_left);
  const nextDeadline = deadlines.find(d => d.days_left >= 0), dueThisWeek = deadlines.filter(d => d.days_left >= 0 && d.days_left <= 7).length;
  const events = upcomingEvents(data.events?.items, today), techEvents = upcomingEvents(data.tech?.events, today, 45).sort((a, b) => String(a.start).localeCompare(String(b.start)));
  const jobs = pickJobs(data.jobs), students = (data.jobs || []).filter(job => job.flags?.includes('student-job')).length;
  const work = data.work || {}, news = data.news || [], lead = news.find(item => item.picture?.url) || news[0], others = news.filter(item => item !== lead).slice(0, 4);
  const briefRun = data.tasks?.brief, savedNews = data.saved_news || [], savedJobs = data.saved_jobs || [];
  const lastQuestion = [...(data.chat || [])].reverse().find(message => message.role === 'user');

  const summary = [
    weather && `${weather.condition[0].toUpperCase()}${weather.condition.slice(1)}, ${weather.low}–${weather.high} °C`,
    dueThisWeek ? `${dueThisWeek} ${dueThisWeek === 1 ? 'deadline' : 'deadlines'} this week` : 'nothing due this week',
    data.jobs?.length ? `${data.jobs.length} open roles` : null,
    events.length ? `${events.length} ${events.length === 1 ? 'event' : 'events'} coming up` : null,
  ].filter(Boolean).join(' · ');

  async function send(e) {
    e.preventDefault();
    const text = question.trim();
    if (!text || data.busy) return;
    setQuestion('');
    await ask(text);
  }

  return <div className="today">
    <section className={`hero ink-${ink}`}>
      <Painting seed={seedFrom(`${today}-${data.home?.city || 'Trier'}`)} hour={hour} condition={weather?.condition || ''} onPainted={result => setInk(result.ink)} />
      <div className="hero-shade" aria-hidden="true" />
      <div className="hero-inner">
        <div className="hero-copy">
          <p className="hero-date">{niceDate(today, { weekday: 'long', day: 'numeric', month: 'long' })} · {data.home?.city || 'Trier'}</p>
          <h1>{greeting}, Dhiraj.</h1>
          <p className="hero-summary">{summary}</p>
        </div>
        <div className="hero-side">
          <button className="hero-refresh" disabled={data.refresh.running} onClick={() => act('/api/refresh', {})}><ArrowClockwiseIcon size={14} weight="bold" aria-hidden="true" />{data.refresh.running ? 'Refreshing…' : data.refreshed_at ? `Updated ${when(data.refreshed_at)}` : 'Refresh'}</button>
          {weather ? <div className="hero-weather">
            <WeatherIcon sky={sky} night={night} size={34} weight="duotone" />
            <div><strong>{weather.high}°</strong><span>{weather.low}° low{weather.rain != null ? ` · ${weather.rain}% rain` : ''}</span></div>
            {tomorrow && <small>Tomorrow {tomorrow.condition}, {tomorrow.low}–{tomorrow.high} °C</small>}
          </div> : <div className="hero-weather empty-weather"><small>{data.refresh.running ? 'Checking the forecast…' : 'Refresh to get the forecast'}</small></div>}
        </div>
      </div>
      {data.refresh.running && <p className="hero-status"><span className="dot pulse" />{data.refresh.message}</p>}
    </section>

    <form className="capture" onSubmit={send}>
      <ChatCircleDotsIcon size={18} weight="bold" aria-hidden="true" />
      <input value={question} onChange={e => setQuestion(e.target.value)} placeholder="Ask Atlas anything, or tell it something to remember…" aria-label="Ask Atlas" />
      <div className="capture-actions">
        <button type="button" onClick={() => setModal('work')}><ClockIcon size={14} weight="bold" aria-hidden="true" />Log shift</button>
        <button type="button" onClick={() => setModal('deadline')}><PlusIcon size={14} weight="bold" aria-hidden="true" />Deadline</button>
        <button type="button" onClick={() => navigate('chat')}><EnvelopeSimpleIcon size={14} weight="bold" aria-hidden="true" />Explain a letter</button>
        <button type="submit" className="capture-send" disabled={!question.trim() || data.busy} aria-label="Send to Ask Atlas"><ArrowUpIcon size={15} weight="bold" /></button>
      </div>
    </form>

    {data.profile_incomplete && <div className="profile-nudge"><span><strong>Make Atlas yours.</strong> Add your German level, skills and plans so advice and job picks fit you.</span><button onClick={() => navigate('settings')}>Set up profile<ArrowUpRightIcon size={13} weight="bold" aria-hidden="true" /></button></div>}

    <div className="glance-row">
      <Glance label="Next deadline" tone={nextDeadline && nextDeadline.days_left <= 7 ? 'warm' : ''} value={nextDeadline ? (nextDeadline.days_left === 0 ? 'Today' : `${nextDeadline.days_left} ${nextDeadline.days_left === 1 ? 'day' : 'days'}`) : 'None'} detail={nextDeadline ? nextDeadline.title : 'Nothing on your radar'} onClick={() => navigate('admin')} />
      <Glance label="Work days left" value={`${Math.round(work.remaining ?? 140)}`} progress={work.limit ? ((work.limit - (work.remaining ?? work.limit)) / work.limit) * 100 : null} detail={`of ${work.limit || 140} in ${work.year || new Date(today).getFullYear()} · ${work.used || 0} used`} onClick={() => navigate('admin')} />
      <Glance label="Open roles" value={data.jobs?.length || 0} detail={students ? `${students} student ${students === 1 ? 'role' : 'roles'}` : 'Refresh to check boards'} onClick={() => navigate('jobs')} />
      <Glance label="This week" value={events.length} detail={events[0] ? `Next: ${events[0].title}` : 'No events found yet'} onClick={() => navigate('events')} />
    </div>

    <div className="bento">
      <Tile icon={SparkleIcon} title="Morning brief" className="t-brief">
        {briefRun && !['done', 'error', 'cancelled'].includes(briefRun.status)
          ? (briefRun.text ? <Markdown linkAction={saveLink}>{briefRun.text}</Markdown> : <div className="thinking"><span className="dot pulse" />{briefRun.status === 'loading' ? 'Getting Gemma ready…' : 'Gathering news, jobs and events…'}</div>)
          : data.brief ? <>{briefRun?.status === 'error' && <p className="form-error">{briefRun.text}</p>}<div className="brief-text"><Markdown linkAction={saveLink}>{data.brief.text}</Markdown></div><footer className="tile-foot"><span>Prepared {when(data.brief.at)}</span><button className="tile-link" disabled={data.busy} onClick={() => act('/api/brief', {})}>Write again<ArrowClockwiseIcon size={13} weight="bold" aria-hidden="true" /></button></footer></>
          : <div className="brief-empty"><p>News, jobs, events and reminders, written up as one short English brief.</p><button className="pill-button" disabled={stoppingModel || (!data.busy && !data.refreshed_at)} onClick={() => data.busy ? stopModel() : act('/api/brief', {})}>{data.busy ? <PauseIcon size={14} weight="bold" /> : <SparkleIcon size={14} weight="bold" />}{stoppingModel ? 'Stopping…' : data.busy ? 'Stop Gemma' : 'Write my brief'}</button>{briefRun?.status === 'error' && <p className="form-error">{briefRun.text}</p>}<small>{data.settings.auto_brief ? 'Written automatically each morning while Hermes is on.' : 'Written by Gemma through Hermes.'}</small></div>}
      </Tile>

      <Tile icon={ForkKnifeIcon} title="Mensa today" className="t-mensa"><Mensa data={data} /></Tile>

      <Tile icon={NewspaperIcon} title="Around you" action="All news" onAction={() => navigate('news')} className="t-news">
        {!news.length ? <p className="tile-empty">Headlines appear after your sources refresh.</p> : <div className="news-layout">
          {lead && <a className="news-lead" href={safeLink(lead.article_url || lead.url)} target="_blank" rel="noreferrer">
            {lead.picture?.url && <span className="news-lead-image" style={{ backgroundImage: `url("${lead.picture.url.replace(/"/g, '%22')}")` }} role="img" aria-label="" />}
            <span className="news-kicker">{newsRegions[lead.ring]} · {lead.source.replace('Google News: ', '')}</span>
            <strong>{lead.title_en || lead.title}</strong>
          </a>}
          <ol className="news-rest">{others.map(item => <li key={item.url}><a href={safeLink(item.article_url || item.url)} target="_blank" rel="noreferrer"><span className="news-kicker">{newsRegions[item.ring]} · {item.source.replace('Google News: ', '')}</span><strong>{item.title_en || item.title}</strong>{item.translation_needed && <small>Original headline · translation pending</small>}</a></li>)}</ol>
        </div>}
      </Tile>

      <Tile icon={BriefcaseIcon} title="Roles for you" action={data.jobs?.length ? `All ${data.jobs.length}` : null} onAction={() => navigate('jobs')} className="t-jobs">
        {jobs.length ? <ul className="row-list">{jobs.map(job => <li key={job.id}><a href={safeLink(job.url)} target="_blank" rel="noreferrer"><span className="mark">{(job.company || '?').slice(0, 1)}</span><span className="row-copy"><strong>{job.title_en || job.title}</strong><small>{[job.company, job.city || job.where, distanceText(job)].filter(Boolean).join(' · ')}</small></span>{job.flags?.includes('student-job') && <span className="chip">Student</span>}</a></li>)}</ul> : <p className="tile-empty">{data.refresh.running ? 'Checking your job boards…' : 'Refresh to see matching roles.'}</p>}
        {data.job_market?.total > 0 && data.job_market.pay?.hourly && <p className="tile-note">Students earn about €{data.job_market.pay.hourly.median}/h · most asked: {data.job_market.skills.slice(0, 3).map(row => row.name).join(', ')}</p>}
      </Tile>

      <Tile icon={CalendarBlankIcon} title="Coming up" action="Life admin" onAction={() => navigate('admin')} className="t-deadlines">
        {deadlines.length ? <ul className="row-list">{deadlines.slice(0, 4).map((d, i) => <li key={i}><div><DateChip date={d.date} /><span className="row-copy"><strong>{d.title}</strong><small className={d.days_left <= 7 ? 'soon' : ''}>{d.days_left === 0 ? 'Today' : d.days_left < 0 ? `${-d.days_left} days overdue` : `In ${d.days_left} days`}</small></span></div></li>)}</ul> : <p className="tile-empty">No deadlines yet. Add your permit, semester fees or tax dates so nothing sneaks up on you.</p>}
        <button className="add-row" onClick={() => setModal('deadline')}><PlusIcon size={13} weight="bold" aria-hidden="true" />Add a deadline</button>
      </Tile>

      <Tile icon={TicketIcon} title="Out and about" action="All events" onAction={() => navigate('events')} className="t-events">
        {events.length ? <ul className="row-list">{events.slice(0, 4).map(event => <li key={event.id}><a href={safeLink(event.url)} target="_blank" rel="noreferrer"><DateChip date={dayDiff(today, event.start) < 0 ? today : event.start} /><span className="row-copy"><strong>{event.title}</strong><small>{dayDiff(today, event.start) < 0 && event.end ? `Until ${niceDate(event.end)} · ` : ''}{event.venue && !/^see /i.test(event.venue) ? event.venue : event.city}</small></span></a></li>)}</ul> : <p className="tile-empty">Nothing found for the next 7 days.</p>}
      </Tile>

      <Tile icon={CodeIcon} title="Tech nearby" action="Tech" onAction={() => navigate('tech')} className="t-tech">
        {techEvents.length ? <ul className="row-list">{techEvents.slice(0, 3).map(event => <li key={event.id}><a href={safeLink(event.url)} target="_blank" rel="noreferrer"><DateChip date={dayDiff(today, event.start) < 0 ? today : event.start} /><span className="row-copy"><strong>{event.title}</strong><small>{event.city}{event.category ? ` · ${event.category}` : ''}</small></span></a></li>)}</ul> : <p className="tile-empty">No tech events in the next weeks.</p>}
      </Tile>

      <Tile icon={BookmarkSimpleIcon} title="Your collection" className="t-memory">
        <div className="memory-grid">
          <button onClick={openSaved}><strong>{savedNews.length}</strong><span>saved stories</span></button>
          <button onClick={() => navigate('jobs')}><strong>{savedJobs.length}</strong><span>saved roles</span></button>
          <button onClick={() => navigate('admin')}><strong>{(data.worklog || []).length}</strong><span>shifts logged</span></button>
          <button onClick={() => navigate('admin')}><strong>{(data.deadlines || []).length}</strong><span>deadlines</span></button>
        </div>
        {lastQuestion && <button className="last-question" onClick={() => navigate('chat')}><small>Last asked</small><span>{lastQuestion.text.slice(0, 110)}{lastQuestion.text.length > 110 ? '…' : ''}</span></button>}
      </Tile>
    </div>

    <footer className="today-foot"><span>{(data.sources || []).filter(s => s.ok && !s.skipped).length} sources working · {(data.sources || []).filter(s => !s.ok).length} need attention</span><button onClick={() => navigate('settings')}>Source status<ArrowUpRightIcon size={12} weight="bold" aria-hidden="true" /></button></footer>
  </div>;
}
