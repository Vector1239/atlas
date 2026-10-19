// Shared map maths: a usable pin, and straight-line distance from home in Trier.
export function validLocation(location) {
  return !!location && Number.isFinite(location.lat) && Number.isFinite(location.lon) && Math.abs(location.lat) <= 90 && Math.abs(location.lon) <= 180;
}
export function cityDistance(location) {
  if (!validLocation(location)) return null;
  const rad = x => x * Math.PI / 180;
  const lat = rad(location.lat - 49.75565), lon = rad(location.lon - 6.63935);
  const a = Math.sin(lat / 2) ** 2 + Math.cos(rad(49.75565)) * Math.cos(rad(location.lat)) * Math.sin(lon / 2) ** 2;
  return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(Math.max(0, 1 - a)));
}
