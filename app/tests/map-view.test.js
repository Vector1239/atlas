import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { savedHome, defaultHome, withHomeBounds, containsPoint, overlapsLabel } from '../src/map-view.js';

test('home comes from saved city coordinates; invalid locations have an honest fallback',()=>{
 assert.deepEqual(savedHome({city:'Trier',lat:49.7499,lon:6.6371}),defaultHome);
 assert.deepEqual(savedHome({city:'Invalid',lat:Infinity,lon:6}),defaultHome);
 const points=[[52.5244,13.4105]];
 assert.deepEqual(withHomeBounds(points,defaultHome),[points[0],[49.7499,6.6371]]);
 assert.equal(points.length,1);
});
test('labels stay on the correct country, including polygon holes and island groups',()=>{
 const outer=[[0,0],[10,0],[10,10],[0,10],[0,0]], hole=[[2,2],[4,2],[4,4],[2,4],[2,2]];
 assert.equal(containsPoint({type:'Polygon',coordinates:[outer,hole]},{lat:1,lon:1}),true);
 assert.equal(containsPoint({type:'Polygon',coordinates:[outer,hole]},{lat:3,lon:3}),false);
 assert.equal(containsPoint({type:'MultiPolygon',coordinates:[[outer,hole]]},{lat:12,lon:3}),false);
 assert.equal(overlapsLabel({x:20,y:20},20,20,[{left:10,right:40,top:5,bottom:30}]),null);
});
test('offline map contains European country outlines and all 16 German states',()=>{
 const map=JSON.parse(fs.readFileSync(new URL('../content/political-map.json',import.meta.url)));
 assert.equal(map.license,'public domain');
 assert.equal(map.states.features.filter(feature=>feature.properties.country==='DE').length,16);
 for(const code of ['DEU','FRA','BEL','LUX','NLD','PRT'])assert.ok(map.countries.features.some(feature=>feature.properties.code===code),code);
 const germany=map.countries.features.find(feature=>feature.properties.code==='DEU');
 assert.ok(containsPoint(germany.geometry,defaultHome));
 assert.ok(map.cities.some(city=>city.name==='Berlin'));
});
