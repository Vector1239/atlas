import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { CrosshairIcon } from '@phosphor-icons/react';
import basemapURL from '../content/political-map.json?url';
import { containsPoint, overlapsLabel, withHomeBounds } from './map-view.js';

export const mapPresets = { trier:[[49.15,5.65],[50.5,8.1]], germany:[[47.1,5.8],[55.05,15.2]], europe:[[37.5,-10.1],[56,18]] };
const element = (className, text) => { const node=document.createElement('span'); node.className=className; node.textContent=text; return node; };

export default function DiscoveryMap({ groups, selected, onSelect, onBounds, onHome, scope, focus, home }) {
  const host=useRef(null), map=useRef(null), pins=useRef(null), geography=useRef(null), labels=useRef(null), refreshLabels=useRef(()=>{}), callbacks=useRef({onSelect,onBounds,onHome}), currentGroups=useRef(groups);
  const [outlineError,setOutlineError]=useState(false), [loaded,setLoaded]=useState(false), [attempt,setAttempt]=useState(0), [homeOutside,setHomeOutside]=useState(false);
  callbacks.current={onSelect,onBounds,onHome}; currentGroups.current=groups;
  useEffect(()=>{
    const instance=L.map(host.current,{scrollWheelZoom:false,minZoom:3,maxZoom:11,maxBounds:[[29,-27],[74,52]],maxBoundsViscosity:.8,zoomSnap:.25}); map.current=instance;
    instance.attributionControl.setPrefix(false);
    instance.attributionControl.addAttribution('<a href="https://www.naturalearthdata.com/" target="_blank" rel="noreferrer">Natural Earth</a> · Approximate city locations');
    instance.createPane('countries').style.zIndex='210'; instance.createPane('states').style.zIndex='220'; instance.createPane('countryBorders').style.zIndex='230';
    instance.createPane('placeLabels').style.zIndex='400'; instance.getPane('placeLabels').style.pointerEvents='none';
    instance.createPane('homeMarker').style.zIndex='690';
    pins.current=L.layerGroup().addTo(instance); labels.current=L.layerGroup().addTo(instance);
    L.control.scale({imperial:false,position:'bottomleft',maxWidth:90}).addTo(instance);
    const changed=()=>{ const b=instance.getBounds(); callbacks.current.onBounds({north:b.getNorth(),south:b.getSouth(),east:b.getEast(),west:b.getWest()}); setHomeOutside(!b.contains([home.lat,home.lon])); refreshLabels.current(); };
    instance.on('moveend',changed);
    instance.fitBounds(withHomeBounds(mapPresets.trier,home),{padding:[45,45],animate:false});
    const resize=new ResizeObserver(()=>instance.invalidateSize()); resize.observe(host.current);
    return ()=>{resize.disconnect(); instance.remove(); map.current=null;};
  },[home.lat,home.lon]);
  useEffect(()=>{
    const instance=map.current; if(!instance)return;
    const node=element('home-dot','');
    const marker=L.marker([home.lat,home.lon],{pane:'homeMarker',keyboard:true,title:`Home · ${home.city}. Saved base, approximate city location.`,zIndexOffset:1500,icon:L.divIcon({className:'home-marker',html:node,iconSize:[18,18],iconAnchor:[9,9]})});
    marker.bindTooltip(element('home-label-text',`Home · ${home.city}`),{permanent:true,direction:'bottom',offset:[0,12],className:'home-map-label'}).addTo(instance);
    return ()=>marker.remove();
  },[home.lat,home.lon,home.city]);
  useEffect(()=>{
    const instance=map.current; if(!instance)return;
    const controller=new AbortController(); setOutlineError(false); setLoaded(false);
    let countryFill,stateLines,countryLines;
    fetch(basemapURL,{signal:controller.signal}).then(response=>{if(!response.ok)throw Error('Map unavailable');return response.json();}).then(data=>{
      if(controller.signal.aborted)return; geography.current=data;
      countryFill=L.geoJSON(data.countries,{pane:'countries',interactive:false,style:feature=>({stroke:false,fillColor:feature.properties.code==='DEU'?'#eff1e9':'#f8f8f4',fillOpacity:1})}).addTo(instance);
      stateLines=L.geoJSON(data.states,{pane:'states',interactive:false,style:{color:'#96a58d',weight:1.25,opacity:.95,dashArray:'4 4',fill:false}}).addTo(instance);
      countryLines=L.geoJSON(data.countries,{pane:'countryBorders',interactive:false,style:{color:'#7a8b84',weight:1.7,opacity:.9,fill:false}}).addTo(instance);
      refreshLabels.current=()=>{
        if(!map.current || !labels.current)return;
        labels.current.clearLayers();
        const bounds=instance.getBounds(),zoom=instance.getZoom(),size=instance.getSize();
        stateLines.setStyle({opacity:zoom>=5?.95:0}); countryLines.setStyle({weight:zoom>=7?2:1.5});
        const hp=instance.latLngToContainerPoint([home.lat,home.lon]);
        const occupied=[{left:hp.x-50,right:hp.x+70,top:hp.y-20,bottom:hp.y+48}, ...currentGroups.current.map(group=>{const p=instance.latLngToContainerPoint([group.location.lat,group.location.lon]);return{left:p.x-22,right:p.x+22,top:p.y-22,bottom:p.y+22};})];
        const add=(name,latlon,kind,width,offset=0)=>{
          if(!bounds.contains(latlon))return false;
          const point=instance.latLngToContainerPoint(latlon); point.x+=offset;
          if(point.x<width/2+12||point.x>size.x-width/2-12||point.y<22||point.y>size.y-25)return false;
          const box=overlapsLabel(point,width,22,occupied); if(!box)return false;
          occupied.push(box);
          const location=instance.containerPointToLatLng(point);
          L.marker(location,{pane:'placeLabels',interactive:false,keyboard:false,icon:L.divIcon({className:`political-label ${kind}`,html:element('',name),iconSize:[width,22],iconAnchor:[width/2,11]})}).addTo(labels.current);
          return true;
        };
        // Fit area names inside the correct polygon and avoid the listing pins.
        const areaLabel=(feature,kind,width)=>{
          const candidates=[feature.properties.label];
          if(zoom>=6){for(const y of [.25,.5,.75])for(const x of [.2,.4,.6,.8])candidates.push([bounds.getSouth()+(bounds.getNorth()-bounds.getSouth())*y,bounds.getWest()+(bounds.getEast()-bounds.getWest())*x]);}
          for(const point of candidates){
            if(!bounds.contains(point)||!containsPoint(feature.geometry,{lat:point[0],lon:point[1]}))continue;
            const screen=instance.latLngToContainerPoint(point);
            const sides=[instance.containerPointToLatLng([screen.x-width/2,screen.y]),instance.containerPointToLatLng([screen.x+width/2,screen.y])];
            if(sides.some(p=>!containsPoint(feature.geometry,{lat:p.lat,lon:p.lng})))continue;
            if(add(feature.properties.name,point,kind,width))break;
          }
        };
        if(zoom>=6){for(const feature of data.states.features){if(feature.properties.country==='DE')areaLabel(feature,'state',Math.max(75,feature.properties.name.length*5.3));}}
        for(const feature of data.countries.features)areaLabel(feature,'country',Math.max(55,feature.properties.name.length*(zoom<6?7:7.5)));
        for(const group of currentGroups.current){const width=Math.max(55,group.city.length*5.6);add(group.city,[group.location.lat,group.location.lon],'city',width,width/2+25);}
        if(zoom>=5){for(const city of [...data.cities].sort((a,b)=>b.population-a.population)){
          if(city.population<(zoom>=7?30000:250000))continue;
          if(currentGroups.current.some(group=>Math.abs(group.location.lat-city.lat)<.08&&Math.abs(group.location.lon-city.lon)<.08))continue;
          add(city.name,[city.lat,city.lon],'city',Math.max(55,city.name.length*5.8));
        }}
      };
      setLoaded(true); refreshLabels.current();
    }).catch(error=>{if(error.name!=='AbortError')setOutlineError(true);});
    return()=>{controller.abort();countryFill?.remove();stateLines?.remove();countryLines?.remove();refreshLabels.current=()=>{};};
  },[attempt,home.lat,home.lon]);
  useEffect(()=>{if(map.current)map.current.fitBounds(withHomeBounds(scope.bounds || mapPresets[scope.name],home),{padding:[60,60],maxZoom:9,animate:false});},[scope,home.lat,home.lon]);
  useEffect(()=>{if(focus && map.current)map.current.fitBounds(withHomeBounds([[focus.lat,focus.lon]],home),{padding:[80,80],maxZoom:9,animate:false});},[focus,home.lat,home.lon]);
  useEffect(()=>{
    if(!pins.current)return; pins.current.clearLayers();
    groups.forEach(group=>{
      const nearHome=Math.abs(group.location.lat-home.lat)<.025&&Math.abs(group.location.lon-home.lon)<.025;
      const marker=L.marker([group.location.lat,group.location.lon],{title:`${group.city}: ${group.jobs} jobs, ${group.events} events. City centre, approximate.`,keyboard:true,icon:L.divIcon({className:`explore-pin ${group.jobs&&group.events?'mixed':group.events?'events':'jobs'} ${selected===group.key?'selected':''} ${nearHome?'near-home':''}`,html:element('',String(group.jobs+group.events)),iconSize:[34,34],iconAnchor:nearHome?[17,56]:[17,17]})});
      marker.bindTooltip(element('',`${group.city} · ${group.jobs} jobs · ${group.events} events`),{direction:'top'}).on('click',()=>callbacks.current.onSelect(group)).addTo(pins.current);
    }); refreshLabels.current();
  },[groups,selected,home.lat,home.lon]);
  return <div className="explore-map-wrap"><div className="explore-map" ref={host} role="region" aria-label="Political map of jobs and events, with country and state borders and your saved home location. Use arrow keys to pan, plus and minus to zoom." />
    <button className={`map-home-button ${homeOutside?'outside':''}`} onClick={()=>callbacks.current.onHome()} title={`Return to your saved base in ${home.city}. This is a city location, not live GPS.`}><CrosshairIcon size={17} weight="bold" /><span><strong>Home · {home.city}</strong><small>{homeOutside?'Outside this view · back to home':'Saved city location'}</small></span>{homeOutside&&<span aria-hidden="true">↗</span>}</button>
    {!loaded&&!outlineError&&<div className="map-loading" role="status">Loading map…</div>}
    {outlineError&&<div className="map-error" role="status">Map outlines couldn’t load. Listings remain available. <button onClick={()=>setAttempt(value=>value+1)}>Retry map</button></div>}
  </div>;
}
