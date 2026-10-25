import test from 'node:test';
import assert from 'node:assert/strict';
import { distanceFrom, groupTechEvents, initialTechFilters, selectTech } from '../src/tech-filters.js';
const home = { lat:49.7499, lon:6.6371 };
const tech = { events:[
  { title:'Near conference',id:'near',kind:'conference',city:'Trier',country:'Germany',location:home,start:'2026-10-20',end:'2026-10-21' },
  { title:'Hackathon',id:'hack',kind:'hackathon',city:'Berlin',country:'Germany',location:{lat:52.52,lon:13.4},start:'2026-11-27',end:'2026-11-29' },
  { title:'Online workshop',id:'online',kind:'event',online:true,start:'2026-10-22',end:'2026-10-22' },
  { title:'Unknown venue',id:'unknown',kind:'conference',city:'Unknown',start:'2026-10-23',end:'2026-10-23' },
  { title:'Expired',id:'old',kind:'conference',location:home,start:'2026-01-01',end:'2026-01-01' }
] };
test('radius filters exclude unknown and online distances and use the selected origin', () => {
  assert.deepEqual(selectTech(tech,{...initialTechFilters,distance:'50'},home,'2026-10-17').map(r => r.id),['near']);
  assert.deepEqual(selectTech(tech,{...initialTechFilters,distance:'50'},tech.events[1].location,'2026-10-17').map(r => r.id),['hack']);
  assert.equal(distanceFrom(null,home),null);
});
test('type, period and online filters combine without showing expired events', () => {
  assert.equal(selectTech(tech,initialTechFilters,home,'2026-10-17').length,4);
  assert.equal(selectTech(tech,{...initialTechFilters,kind:'hackathon',period:'7'},home,'2026-10-17').length,0);
  assert.deepEqual(selectTech(tech,{...initialTechFilters,area:'online'},home,'2026-10-17').map(r => r.id),['online']);
});
test('source filters match duplicate provenance and searches include topics', () => {
  const listings = { events:[{...tech.events[0],source:'Calendar',listed_by:[{name:'MLH'},{name:'Calendar'}],topics:['Robotics']}] };
  assert.equal(selectTech(listings,{...initialTechFilters,source:'MLH',search:'Robotics'},home,'2026-10-17').length,1);
  assert.equal(selectTech(listings,{...initialTechFilters,source:'Devpost'},home,'2026-10-17').length,0);
});

const meetup = { id:'first', title:'Chaostreff', kind:'event', source:'Maschinendeck Trier',
  url:'https://maschinendeck.org/', city:'Trier', country:'Germany', venue:'Vereinsheim',
  location:home, start:'2026-10-20', end:'2026-10-20', time_note:'20:00–23:59 CEST' };
const nextMeetup = { ...meetup, id:'second', start:'2026-10-27', end:'2026-10-27', time_note:'20:00–23:59 CET' };
test('recurring cached listings stack with sorted dates and their individual times and links', () => {
  const rows = [nextMeetup,meetup];
  const before = structuredClone(rows);
  const [group] = groupTechEvents(rows);
  assert.equal(group.start,meetup.start);
  assert.deepEqual(group.occurrences,[meetup,nextMeetup]);
  assert.deepEqual(rows,before);
  assert.equal(groupTechEvents([meetup,nextMeetup,meetup])[0].occurrences.length,2);
});
test('series identity supports separate registration links while distinct series and places stay separate', () => {
  const first = { ...meetup, series_id:'public-calendar-id' };
  const second = { ...nextMeetup, series_id:first.series_id, url:'https://example.org/next-meeting' };
  assert.equal(groupTechEvents([first,second]).length,1);
  for (const change of [ {city:'Berlin'}, {venue:'Another venue'}, {source:'Another club'},
    {series_id:'another-id'}, {title:'Chaostreff 2027'}, {kind:'conference'} ]) {
    assert.equal(groupTechEvents([first,{...second,...change}]).length,2);
  }
  assert.equal(groupTechEvents([meetup,{...nextMeetup,url:'https://other.example/'}]).length,2);
});
test('dates are filtered before stacking and the next date advances after an occurrence ends', () => {
  const listings = {events:[meetup,nextMeetup]};
  const all = groupTechEvents(selectTech(listings,initialTechFilters,home,'2026-10-18'));
  const week = groupTechEvents(selectTech(listings,{...initialTechFilters,period:'7'},home,'2026-10-18'));
  const later = groupTechEvents(selectTech(listings,initialTechFilters,home,'2026-10-21'));
  assert.equal(all.length,1);
  assert.equal(all[0].occurrences.length,2);
  assert.equal(week[0].occurrences.length,1);
  assert.equal(later[0].start,'2026-10-27');
  assert.equal(later[0].id,all[0].id);
  assert.equal(groupTechEvents(selectTech(listings,{...initialTechFilters,city:'Berlin'},home,'2026-10-18')).length,0);
});
test('separate same-day sessions retain their times and listings without identity stay individual', () => {
  const evening = {...meetup,id:'evening',time_note:'21:00–23:59 CEST'};
  assert.equal(groupTechEvents([meetup,evening])[0].occurrences.length,2);
  assert.equal(groupTechEvents([{...meetup,url:undefined},{...nextMeetup,url:undefined}]).length,2);
});

test('events that started earlier but are still running sort as today, not by their old start', () => {
  const running = { title:'Long submission window',id:'running',kind:'hackathon',online:true,start:'2026-09-01',end:'2026-11-30' };
  const tomorrow = { title:'A meetup tomorrow',id:'tomorrow',kind:'event',online:true,start:'2026-10-18',end:'2026-10-18' };
  const today = { title:'Today talk',id:'today',kind:'event',online:true,start:'2026-10-17',end:'2026-10-17' };
  assert.deepEqual(selectTech({events:[tomorrow,today,running]},{...initialTechFilters,sort:'date'},home,'2026-10-17').map(r => r.id),['running','today','tomorrow']);
});

test('the Tech tab opens sorted by date, soonest first, regardless of distance', () => {
  assert.equal(initialTechFilters.sort,'date');
  assert.deepEqual(selectTech(tech,initialTechFilters,home,'2026-10-17').map(r => r.id),['near','online','unknown','hack']);
});
