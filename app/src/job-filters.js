export function selectJobs(jobs, filters, saved = []) {
  const result = jobs.filter(job => {
    const text = `${job.title} ${job.title_en || ''} ${job.company} ${job.where} ${job.city} ${job.source_label}`.toLowerCase();
    return text.includes(filters.search.trim().toLowerCase())
      && (filters.group !== 'student' || job.flags.includes('student-job'))
      && (filters.group !== 'saved' || saved.includes(job.id))
      && (filters.distance === 'any' || job.distance_from_trier != null && job.distance_from_trier <= Number(filters.distance))
      && (filters.city === 'all' || job.city === filters.city)
      && (filters.source === 'all' || job.source_label === filters.source)
      && (filters.workplace !== 'remote' || job.remote)
      && (filters.language === 'all' || job.flags.includes(filters.language === 'english' ? 'english' : 'posting-in-german'))
      && (!filters.hideSenior || !job.flags.includes('senior'));
  });
  return result.sort((a, b) => {
    if (filters.sort === 'newest') return (Date.parse(b.posted) || 0) - (Date.parse(a.posted) || 0);
    if (filters.sort === 'student') {
      const priority = Number(b.flags.includes('student-job')) - Number(a.flags.includes('student-job'));
      if (priority) return priority;
    }
    return (a.distance_from_trier ?? Infinity) - (b.distance_from_trier ?? Infinity) || a.title.localeCompare(b.title);
  });
}

export function distanceLabel(job) {
  if (job.distance_from_trier != null) return `${job.distance_from_trier.toLocaleString('en-GB', { maximumFractionDigits: 1 })} km from Trier · board reported`;
  if (job.distance_km != null && job.distance_origin) return `${job.distance_km} km from ${job.distance_origin}`;
  return 'Distance not provided';
}
