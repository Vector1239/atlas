// A watercolour Moselle-valley landscape for the Today page, painted on a canvas.
// Layers of translucent, randomly deformed polygons build up the soft edges of a wet wash.
// The sky follows the time of day and today's weather; the seed is the date, so the
// painting stays the same all day and changes tomorrow.

export function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function seedFrom(text) {
  let h = 2166136261;
  for (const ch of String(text)) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
  return h >>> 0;
}

export function phaseFor(hour) {
  if (hour >= 6 && hour < 8) return 'dawn';
  if (hour >= 8 && hour < 16) return 'day';
  if (hour >= 16 && hour < 18) return 'dusk';
  return 'night';
}

// Groups Open-Meteo's words ("light rain", "partly cloudy", …) into what the sky shows.
export function skyFor(condition = '') {
  const c = condition.toLowerCase();
  if (/thunder/.test(c)) return 'storm';
  if (/snow/.test(c)) return 'snow';
  if (/rain|drizzle|shower/.test(c)) return 'rain';
  if (/fog/.test(c)) return 'fog';
  if (/overcast/.test(c)) return 'overcast';
  if (/cloud/.test(c)) return 'cloudy';
  return condition ? 'clear' : 'cloudy';
}

const PALETTES = {
  day: { sky: ['#c6dbe3', '#f4efe2'], sun: '#f3d48c', hills: ['#bccab3', '#9aae8f', '#73906b', '#506b4b'], river: '#e2ebe8', ink: 'dark' },
  dawn: { sky: ['#efc4a6', '#f8eadb'], sun: '#f6c98f', hills: ['#cbbcab', '#ab9e88', '#837f64', '#5c5e47'], river: '#f2dccb', ink: 'dark' },
  dusk: { sky: ['#c3a3b7', '#f3cfa6'], sun: '#f1a56c', hills: ['#ab9ca8', '#8d8290', '#6a6575', '#504d5c'], river: '#ecc9b3', ink: 'dark' },
  night: { sky: ['#232c45', '#4a4e69'], sun: '#efe8cf', hills: ['#3e475b', '#333b4d', '#272e3e', '#1c2231'], river: '#5b6280', ink: 'light' },
  cloudy: { sky: ['#d5dbd8', '#efede6'], sun: '#f1e2b6', hills: ['#c2c9bb', '#a3ae9a', '#7f8f77', '#5d6e57'], river: '#e6eae6', ink: 'dark' },
  rain: { sky: ['#bfc7c7', '#e1e2dc'], sun: '#e8e2c8', hills: ['#b4beb2', '#909d8c', '#6e7e6a', '#4e5e4b'], river: '#d7dedc', ink: 'dark' },
};

export function paletteFor(phase, sky) {
  if (phase === 'night') return PALETTES.night;
  if (['rain', 'storm', 'snow'].includes(sky)) return PALETTES.rain;
  if (['overcast', 'fog'].includes(sky) || (sky === 'cloudy' && phase === 'day')) return PALETTES.cloudy;
  return PALETTES[phase];
}

function gaussian(rand) {
  const u = 1 - rand(), v = rand();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

// Splits every edge and nudges the new midpoint: the jagged, bleeding edge of a wash.
function deform(points, depth, variance, rand) {
  let shape = points;
  for (let d = 0; d < depth; d++) {
    const next = [];
    for (let i = 0; i < shape.length; i++) {
      const [ax, ay, av] = shape[i], [bx, by, bv] = shape[(i + 1) % shape.length];
      const length = Math.hypot(bx - ax, by - ay), spread = ((av + bv) / 2) * variance;
      next.push(shape[i], [(ax + bx) / 2 + gaussian(rand) * length * spread, (ay + by) / 2 + gaussian(rand) * length * spread, (av + bv) / 2]);
    }
    shape = next;
  }
  return shape;
}

function fillShape(ctx, points) {
  ctx.beginPath();
  points.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
  ctx.closePath();
  ctx.fill();
}

function wash(ctx, points, color, rand, { layers = 22, alpha = 0.05, variance = 0.32 } = {}) {
  const base = deform(points, 3, variance, rand);
  ctx.save();
  ctx.fillStyle = color;
  ctx.globalAlpha = alpha;
  for (let i = 0; i < layers; i++) fillShape(ctx, deform(base, 2, variance * 0.7, rand));
  ctx.restore();
  return base;
}

function blob(cx, cy, rx, ry, count = 12) {
  return Array.from({ length: count }, (_, i) => {
    const angle = (i / count) * Math.PI * 2;
    return [cx + Math.cos(angle) * rx, cy + Math.sin(angle) * ry, 1];
  });
}

// A ridge across the canvas; its bottom edge sits below the frame so only the crest shows.
function ridge(width, height, baseY, amplitude, rand) {
  const waves = Array.from({ length: 3 }, (_, i) => ({ f: (i + 1) * (0.6 + rand() * 0.9), p: rand() * Math.PI * 2, a: amplitude / (i * 1.6 + 1) }));
  const steps = 22, top = [];
  for (let i = 0; i <= steps; i++) {
    const x = -width * 0.08 + (i / steps) * width * 1.16, t = i / steps;
    const y = baseY + waves.reduce((sum, w) => sum + Math.sin(t * Math.PI * w.f + w.p) * w.a, 0);
    top.push([x, y, 1]);
  }
  return [...top, [width * 1.1, height * 1.3, 0.2], [-width * 0.1, height * 1.3, 0.2]];
}

function paperGrain(ctx, width, height, rand) {
  const tile = document.createElement('canvas');
  tile.width = tile.height = 96;
  const t = tile.getContext('2d'), image = t.createImageData(96, 96);
  for (let i = 0; i < image.data.length; i += 4) {
    const v = 200 + rand() * 55;
    image.data[i] = image.data[i + 1] = image.data[i + 2] = v;
    image.data[i + 3] = 255;
  }
  t.putImageData(image, 0, 0);
  ctx.save();
  ctx.globalCompositeOperation = 'multiply';
  ctx.globalAlpha = 0.07;
  ctx.fillStyle = ctx.createPattern(tile, 'repeat');
  ctx.fillRect(0, 0, width, height);
  ctx.restore();
}

export function paint(canvas, { seed, hour, condition }) {
  const ratio = Math.min(window.devicePixelRatio || 1, 2), width = canvas.clientWidth, height = canvas.clientHeight;
  if (!width || !height) return null;
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const ctx = canvas.getContext('2d');
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  const rand = rng(seed), phase = phaseFor(hour), sky = skyFor(condition), colors = paletteFor(phase, sky);

  const gradient = ctx.createLinearGradient(0, 0, 0, height);
  gradient.addColorStop(0, colors.sky[0]);
  gradient.addColorStop(1, colors.sky[1]);
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, width, height);
  for (let i = 0; i < 3; i++) wash(ctx, blob(width * (0.2 + rand() * 0.6), height * (0.1 + rand() * 0.3), width * 0.35, height * 0.18), colors.sky[i % 2], rand, { layers: 10, alpha: 0.05 });

  if (phase === 'night') {
    ctx.save();
    ctx.fillStyle = '#f5f1df';
    for (let i = 0; i < 70; i++) {
      ctx.globalAlpha = 0.25 + rand() * 0.6;
      ctx.beginPath();
      ctx.arc(rand() * width, rand() * height * 0.55, rand() * 1.1 + 0.3, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  const sunX = width * (phase === 'dawn' ? 0.6 : phase === 'dusk' ? 0.56 : 0.64), sunY = height * (phase === 'day' ? 0.22 : phase === 'night' ? 0.2 : 0.4);
  const visibleSun = !['rain', 'storm', 'snow', 'overcast', 'fog'].includes(sky) || phase === 'night';
  if (visibleSun) {
    const glow = ctx.createRadialGradient(sunX, sunY, 0, sunX, sunY, height * 0.55);
    glow.addColorStop(0, colors.sun + 'aa');
    glow.addColorStop(1, colors.sun + '00');
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, width, height);
    wash(ctx, blob(sunX, sunY, height * 0.065, height * 0.065, 16), colors.sun, rand, { layers: 18, alpha: 0.1, variance: 0.04 });
  }

  const cloudCount = { clear: 1, cloudy: 4, overcast: 6, fog: 4, rain: 5, storm: 7, snow: 5 }[sky] ?? 3;
  const cloudColor = phase === 'night' ? '#6b7088' : ['rain', 'storm'].includes(sky) ? '#b9c0c0' : '#ffffff';
  for (let i = 0; i < cloudCount; i++) {
    const cx = rand() * width, cy = height * (0.08 + rand() * 0.32);
    wash(ctx, blob(cx, cy, width * (0.08 + rand() * 0.12), height * (0.04 + rand() * 0.05), 10), cloudColor, rand, { layers: 16, alpha: 0.07, variance: 0.25 });
  }

  const bases = [0.5, 0.6, 0.72, 0.86], amplitudes = [0.07, 0.08, 0.06, 0.05];
  colors.hills.forEach((color, index) => {
    const shape = ridge(width, height, height * bases[index], height * amplitudes[index], rand);
    const painted = wash(ctx, shape, color, rand, { layers: 20 + index * 3, alpha: 0.055 + index * 0.012, variance: 0.07 });
    if (index === 2) {
      // Vineyard rows on the middle slope, clipped to the hill.
      ctx.save();
      ctx.beginPath();
      painted.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
      ctx.closePath();
      ctx.clip();
      ctx.strokeStyle = colors.hills[3];
      ctx.globalAlpha = 0.12;
      ctx.lineWidth = 1;
      for (let x = -height; x < width + height; x += 9) {
        ctx.beginPath();
        ctx.moveTo(x, height * 0.55);
        ctx.lineTo(x + height * 0.35, height);
        ctx.stroke();
      }
      ctx.restore();
    }
    if (index === 1) {
      // The river: a pale band bending through the valley floor.
      const y = height * 0.8, river = [];
      for (let i = 0; i <= 10; i++) river.push([-width * 0.05 + i * width * 0.11, y + Math.sin(i * 0.8 + rand()) * height * 0.025, 1]);
      for (let i = 10; i >= 0; i--) river.push([-width * 0.05 + i * width * 0.11, y + height * 0.035 + Math.sin(i * 0.8) * height * 0.02, 1]);
      wash(ctx, river, colors.river, rand, { layers: 14, alpha: 0.1, variance: 0.08 });
    }
  });

  if (sky === 'fog') for (let i = 0; i < 4; i++) wash(ctx, blob(rand() * width, height * (0.55 + rand() * 0.3), width * 0.5, height * 0.06), '#f4f3ee', rand, { layers: 12, alpha: 0.08 });
  if (['rain', 'storm'].includes(sky)) {
    ctx.save();
    ctx.strokeStyle = phase === 'night' ? '#c9cde0' : '#7d8a8c';
    ctx.lineWidth = 0.8;
    for (let i = 0; i < 150; i++) {
      const x = rand() * width * 1.1, y = rand() * height, length = 8 + rand() * 12;
      ctx.globalAlpha = 0.08 + rand() * 0.14;
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x - length * 0.3, y + length);
      ctx.stroke();
    }
    ctx.restore();
  }
  if (sky === 'snow') {
    ctx.save();
    ctx.fillStyle = '#ffffff';
    for (let i = 0; i < 120; i++) {
      ctx.globalAlpha = 0.4 + rand() * 0.5;
      ctx.beginPath();
      ctx.arc(rand() * width, rand() * height, 0.8 + rand() * 1.6, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }
  paperGrain(ctx, width, height, rand);
  return { phase, sky, ink: colors.ink };
}
