import test from 'node:test';
import assert from 'node:assert/strict';
import { distanceFrom, initialTechFilters, selectTech } from '../src/tech-filters.js';
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
