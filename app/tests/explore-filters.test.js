import { test } from 'node:test';
import assert from 'node:assert/strict';
import { exploreTotals, exploreView, initialFilters, filtersForScope, selectExplore, groupPlaces, inBounds, cityDistance, placeKey } from '../src/explore-filters.js';
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
 assert.deepEqual(selectExplore(data,{...initialFilters,kind:'events',when:'7'}).map(i=>i.id),['e1']);
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
test('loaded totals and map exclusions reconcile without counting unplaced listings twice', () => {
 const totals=exploreTotals(data), items=selectExplore(data,initialFilters);
 assert.deepEqual(totals,{jobs:2,events:2,total:4});
 const view=exploreView(items,{bounds:{north:50,south:49,east:7,west:6}});
 assert.deepEqual(view.visible.map(item=>item.key),['job:j1','event:e1']);
 assert.equal(view.unplaced,1);
 assert.equal(view.outsideArea,1);
 assert.equal(view.visible.length+view.unplaced+view.outsideArea+view.outsideCity,totals.total);
 assert.deepEqual(exploreTotals({}),{jobs:0,events:0,total:0});
});
test('including all locations restores every filtered item and selected city counts stay disjoint', () => {
 const items=selectExplore(data,initialFilters);
 const all=exploreView(items,{inView:false});
 assert.deepEqual(all.visible,items);
 assert.equal(all.unplaced+all.outsideArea+all.outsideCity,0);
 const city=exploreView(items,{inView:false,selected:placeKey(job)});
 assert.equal(city.visible.length,2);
 assert.equal(city.outsideCity,2);
 assert.equal(city.visible.length+city.outsideCity,items.length);
 const jobs=selectExplore(data,{...initialFilters,kind:'jobs'});
 assert.equal(exploreView(jobs,{inView:false}).visible.length,exploreTotals(data).jobs);
});
test('every locally loaded match remains visible beyond the old twenty-card limit', () => {
 const jobs=Array.from({length:226},(_,i)=>({...job,id:`job-${i}`}));
 const events=Array.from({length:10},(_,i)=>({...event,id:`event-${i}`}));
 const loaded={...data,jobs,events:{items:events}};
 const matches=selectExplore(loaded,initialFilters);
 assert.equal(exploreTotals(loaded).total,236);
 assert.equal(exploreView(matches,{inView:false}).visible.length,236);
 assert.equal(exploreView(matches).visible.filter(item=>item.kind==='job').length,226);
});

test('one Remote preset shows the three remote boards and clears geographic and source constraints', () => {
 const filters = filtersForScope({...initialFilters,kind:'events',city:'Trier',distance:'25',source:'Arbeitnow'}, 'remote');
 const remotes = ['Himalayas','Remote OK','Jobicy'].map((source,i) => ({...job,id:`remote${i}`,source,source_label:source,remote:true,city:'Remote',location:null,distance_from_trier:null}));
 const otherRemote = {...job,id:'otherRemote',source:'Arbeitnow',source_label:'Arbeitnow',remote:true};
 const jobs = [job,...remotes,otherRemote];
 const items = selectExplore({...data,jobs},filters,'remote');
 assert.deepEqual(items.map(i=>i.id),remotes.map(i=>i.id));
 assert.equal(filters.sort,'newest');
 assert.equal(filters.source,'all');
 assert.deepEqual(exploreView(items,{inView:false}).visible,items);
 const home = filtersForScope(filters,'trier');
 assert.equal(home.workplace,'all');
 assert.equal(selectExplore({...data,jobs},home,'trier').length,jobs.length);
});
test('listings sharing an id still get unique keys, so no stale job card lingers when switching to Events', () => {
 const twice={...data,jobs:[job,{...job,title:'Other role'}]};
 const keys=selectExplore(twice,initialFilters).map(i=>i.key);
 assert.equal(new Set(keys).size,keys.length);
});
