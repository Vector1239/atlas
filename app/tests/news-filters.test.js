import { test } from 'node:test';
import assert from 'node:assert/strict';
import { selectNews, initialNewsFilters } from '../src/news-filters.js';
const now=Date.parse('2026-10-17T12:00:00Z');
const items=[
 {title:'Neue Ausstellung',title_en:'New exhibition',source:'Local paper',ring:0,published:'2026-10-16T11:00:00Z',picture:{url:'photo'}},
 {title:'European news',source:'European paper',ring:3,published:'2026-10-17T11:00:00Z'},
 {title:'Undated story',source:'Local paper',ring:0,published:null},
];
test('default news view includes every story, including older, undated and unillustrated stories',()=>{
 const many=Array.from({length:65},(_,index)=>({...items[index%items.length],title:`Story ${index}`}));
 const result=selectNews(many,initialNewsFilters,now);
 assert.equal(result.length,65);
 assert.equal(new Set(result.map(item=>item.title)).size,65);
 assert.ok(result.some(item=>!item.picture));
 assert.ok(result.some(item=>!item.published));
});
test('news searches translated and original titles with region, source and photo filters',()=>{
 assert.deepEqual(selectNews(items,{...initialNewsFilters,search:'exhibition',region:'0',source:'Local paper',photos:true},now),[items[0]]);
 assert.equal(selectNews(items,{...initialNewsFilters,search:'Ausstellung'},now).length,1);
 assert.equal(selectNews(items,{...initialNewsFilters,region:'2'},now).length,0);
 assert.equal(selectNews(items,{...initialNewsFilters,photos:true},now).length,1);
});
test('time filters exclude missing dates; newest/local order stays predictable without mutating sources',()=>{
 const before=items.map(i=>i.title);
 assert.deepEqual(selectNews(items,{...initialNewsFilters,period:'24'},now),[items[1]]);
 assert.equal(selectNews(items,{...initialNewsFilters,sort:'newest'},now)[0],items[1]);
 assert.equal(selectNews(items,initialNewsFilters,now)[0],items[0]);
 assert.deepEqual(items.map(i=>i.title),before);
});
