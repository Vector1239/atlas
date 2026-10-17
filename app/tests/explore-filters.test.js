import { test } from 'node:test';
import assert from 'node:assert/strict';
import { initialFilters, selectExplore, groupPlaces, inBounds, cityDistance } from '../src/explore-filters.js';
const trier = { lat:49.75565, lon:6.63935 }, berlin = { lat:52.52437, lon:13.41053 };
const job = { id:'j1', title:'Analyst', title_en:'Analyst', company:'Team', city:'Trier', source_label:'Board', distance_from_trier:2, flags:['student-job'], location:trier };
const event = { id:'e1', title:'Concert', city:'Trier', source:'City', category:'Music', start:'2026-10-20', location:trier };
const data = { date:'2026-10-17', jobs:[job,{...job,id:'j2',city:'Unknown',location:null,distance_from_trier:null}], saved_jobs:['j1'], events:{items:[event,{...event,id:'e2',city:'Berlin',start:'2026-11-10',location:berlin}]} };
test('mixed results preserve both types and grouped city counts; unknown pins stay unplaced', () => {
 const items=selectExplore(data,initialFilters);
 assert.deepEqual(items.map(i=>i.key),['job:j1','event:e1','job:j2','event:e2']);
 assert.deepEqual(groupPlaces(items).map(g=>[g.city,g.jobs,g.events]),[['Trier',1,1],['Berlin',0,1]]);
 assert.equal(inBounds(null,null),false);
 assert.equal(inBounds(trier,{north:50,south:49,east:7,west:6}),true);
 assert.equal(inBounds(berlin,{north:50,south:49,east:7,west:6}),false);
});
test('layer, radius and event dates combine without treating unknown distance as zero', () => {
 assert.deepEqual(selectExplore(data,{...initialFilters,kind:'events',period:'7'}).map(i=>i.id),['e1']);
 assert.deepEqual(selectExplore(data,{...initialFilters,distance:'25'}).map(i=>i.id),['j1','e1']);
 assert.equal(selectExplore(data,{...initialFilters,kind:'jobs',group:'saved'}).length,1);
 assert.equal(selectExplore(data,{...initialFilters,kind:'events',category:'Culture'}).length,0);
 assert.equal(cityDistance(trier),0);
 assert.ok(cityDistance(berlin)>500);
});
test('searches update both layers and map wraparound remains valid', () => {
 assert.equal(selectExplore(data,{...initialFilters,search:'Berlin'})[0].id,'e2');
 assert.equal(inBounds({lat:0,lon:-175},{north:10,south:-10,west:170,east:190}),true);
 assert.equal(inBounds({lat:0,lon:0},{north:10,south:-10,west:170,east:190}),false);
 assert.equal(inBounds({lat:Infinity,lon:6},null),false);
});
