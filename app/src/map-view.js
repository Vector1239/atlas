import { validLocation } from './explore-filters.js';

export const defaultHome = { lat:49.7499, lon:6.6371, city:'Trier' };
export function savedHome(value) {
  return validLocation(value) ? { lat:value.lat, lon:value.lon, city:value.city || 'Home' } : defaultHome;
}
export function withHomeBounds(points, home) {
  return [...points.filter(point => Array.isArray(point) && Number.isFinite(point[0]) && Number.isFinite(point[1])), [home.lat, home.lon]];
}
export function overlapsLabel(point, width, height, occupied) {
  const box = { left:point.x-width/2, right:point.x+width/2, top:point.y-height/2, bottom:point.y+height/2 };
  if (occupied.some(other => box.left < other.right && box.right > other.left && box.top < other.bottom && box.bottom > other.top)) return null;
  return box;
}
// Keep cities visible even when no listing is available there or a filter hides it.
export function mapCities(cities, places) {
  const result = [...cities];
  for (const place of Object.values(places)) {
    if (!validLocation(place) || result.some(city => Math.abs(city.lat-place.lat)<.04 && Math.abs(city.lon-place.lon)<.04)) continue;
    result.push({name:place.name,lat:place.lat,lon:place.lon,population:0});
  }
  return result.sort((a,b)=>b.population-a.population);
}
export function cityVisible(city, zoom) {
  const population = zoom>=9 ? 0 : zoom>=8 ? 10000 : zoom>=7 ? 30000 : zoom>=6 ? 100000 : zoom>=5 ? 300000 : 1500000;
  return zoom>=4 && city.population>=population;
}
export function containsPoint(geometry, point) {
  const inRing = ring => {
    let inside = false;
    for (let i=0,j=ring.length-1;i<ring.length;j=i++) {
      const [xi,yi]=ring[i], [xj,yj]=ring[j];
      if ((yi>point.lat)!==(yj>point.lat) && point.lon<(xj-xi)*(point.lat-yi)/(yj-yi)+xi) inside=!inside;
    }
    return inside;
  };
  const inPolygon = polygon => inRing(polygon[0]) && !polygon.slice(1).some(inRing);
  return geometry.type === 'Polygon' ? inPolygon(geometry.coordinates) : geometry.type === 'MultiPolygon' && geometry.coordinates.some(inPolygon);
}
