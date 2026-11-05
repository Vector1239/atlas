// Plain helpers behind the Today page, kept apart from React so they can be tested.
const DAY = 86400000;

// "today: light rain, 6–11 °C, rain chance 80%, wind up to 20 km/h" → its parts.
export function parseWeather(line = '') {
  const match = String(line).match(/^(\w+):\s*([^,]+),\s*(-?\d+)–(-?\d+) °C(?:, rain chance (\d+)%)?(?:, wind up to (\d+))?/);
  if (!match) return null;
  return { label: match[1], condition: match[2], low: Number(match[3]), high: Number(match[4]), rain: match[5] == null ? null : Number(match[5]), wind: match[6] == null ? null : Number(match[6]) };
}

export const dayDiff = (from, to) => Math.round((new Date(to) - new Date(from)) / DAY);

// Events that start in the next `days`, or are already running.
export function upcomingEvents(items, today, days = 7) {
  return (items || []).filter(event => {
    const start = dayDiff(today, event.start), end = event.end ? dayDiff(today, event.end) : start;
    return end >= 0 && start <= days;
  }).sort((a, b) => (a.area === 'Trier' ? 0 : 1) - (b.area === 'Trier' ? 0 : 1) || String(a.start).localeCompare(String(b.start)));
}

export function pickJobs(jobs, count = 4) {
  const rank = job => (job.flags?.includes('student-job') ? 0 : 1) * 1e6 + (job.distance_km ?? 5e5);
  return [...(jobs || [])].sort((a, b) => rank(a) - rank(b)).slice(0, count);
}
