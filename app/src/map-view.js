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
