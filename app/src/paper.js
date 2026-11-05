// Watercolour paper for the whole app, painted once on the device with canvas 2D.
// Grain: speckled noise plus short paper fibres. Stains: stacked low-alpha deformed
// polygons (Tyler Hobbs' technique), each edge stroked a little darker the way pigment
// dries at the rim of a wash, with lighter "backrun" blooms lifted out of the middle.
// Coffee rings: jittered arcs, darker on one side. Everything becomes data URLs in CSS
// custom properties, so pages only reference var(--paper-grain) and var(--stain-*).
import { rng, seedFrom } from './painting.js';

const INKS = [
  [192, 146, 70],   // ochre
  [200, 166, 92],   // gold
  [182, 126, 80],   // tea
  [196, 160, 112],  // sand
  [150, 160, 108],  // sage
  [172, 124, 88],   // umber
];

function gaussian(rand) {
  const u = 1 - rand(), v = rand();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

function deform(points, depth, variance, rand) {
  let shape = points;
  for (let d = 0; d < depth; d++) {
    const next = [];
    for (let i = 0; i < shape.length; i++) {
      const [ax, ay] = shape[i], [bx, by] = shape[(i + 1) % shape.length], length = Math.hypot(bx - ax, by - ay);
      next.push(shape[i], [(ax + bx) / 2 + gaussian(rand) * length * variance, (ay + by) / 2 + gaussian(rand) * length * variance]);
    }
    shape = next;
  }
  return shape;
}

function trace(ctx, points) {
  ctx.beginPath();
  points.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
  ctx.closePath();
}

function circle(cx, cy, r, count = 10) {
  return Array.from({ length: count }, (_, i) => [cx + Math.cos((i / count) * Math.PI * 2) * r, cy + Math.sin((i / count) * Math.PI * 2) * r]);
}

// Stains are painted on opaque white and laid over the paper with multiply blending.
// Painting faint washes onto a transparent canvas instead shifts their hue (green, pink),
// because 8-bit premultiplied alpha can't hold colour at such low opacity.
function canvasOf(width, height, white = false) {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  if (white) { ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, width, height); }
  return [canvas, ctx];
}

// One wash with a darker dried rim and a few lifted blooms.
export function bloom(ctx, cx, cy, radius, ink, rand, strength = 1) {
  const [r, g, b] = ink, base = deform(circle(cx, cy, radius, 9), 3, 0.42, rand);
  for (let i = 0; i < 16; i++) {
    const layer = deform(base, 3, 0.22, rand);
    trace(ctx, layer);
    ctx.fillStyle = `rgba(${r},${g},${b},${0.034 * strength})`;
    ctx.fill();
    if (i % 3 === 0) {
      ctx.strokeStyle = `rgba(${r * 0.78 | 0},${g * 0.7 | 0},${b * 0.62 | 0},${0.06 * strength})`;
      ctx.lineWidth = 1 + rand() * 1.2;
      ctx.stroke();
    }
  }
  ctx.save();
  // Backruns: lighter pools where water pushed the pigment back.
  ctx.globalCompositeOperation = 'source-over';
  for (let i = 0; i < 3; i++) {
    const lift = deform(circle(cx + gaussian(rand) * radius * 0.3, cy + gaussian(rand) * radius * 0.3, radius * (0.15 + rand() * 0.2), 8), 3, 0.3, rand);
    trace(ctx, lift);
    ctx.fillStyle = 'rgba(255,255,255,0.22)';
    ctx.fill();
  }
  ctx.restore();
}

// A cup ring: a broken rim, heavier on one side, with a faint tint inside.
export function ring(ctx, cx, cy, radius, ink, rand, strength = 1) {
  const [r, g, b] = ink, heavy = rand() * Math.PI * 2;
  ctx.save();
  trace(ctx, deform(circle(cx, cy, radius * 0.96, 24), 2, 0.05, rand));
  ctx.fillStyle = `rgba(${r},${g},${b},${0.025 * strength})`;
  ctx.fill();
  for (let pass = 0; pass < 7; pass++) {
    const start = rand() * Math.PI * 2, sweep = Math.PI * (0.8 + rand() * 1.3), steps = 80;
    ctx.beginPath();
    for (let i = 0; i <= steps; i++) {
      const angle = start + (i / steps) * sweep, wobble = radius * (1 + Math.sin(angle * 3 + pass) * 0.012 + gaussian(rand) * 0.004);
      const x = cx + Math.cos(angle) * wobble, y = cy + Math.sin(angle) * wobble;
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    }
    const weight = 0.5 + 0.5 * Math.cos(start + sweep / 2 - heavy);
    ctx.strokeStyle = `rgba(${r * 0.8 | 0},${g * 0.7 | 0},${b * 0.6 | 0},${(0.05 + weight * 0.09) * strength})`;
    ctx.lineWidth = 0.8 + weight * 2.4;
    ctx.stroke();
  }
  ctx.restore();
}

export function grainTile(seed = 1, size = 180) {
  const rand = rng(seed), [canvas, ctx] = canvasOf(size, size), image = ctx.createImageData(size, size);
  for (let i = 0; i < image.data.length; i += 4) {
    const v = rand();
    image.data[i] = 120; image.data[i + 1] = 100; image.data[i + 2] = 60;
    image.data[i + 3] = v > 0.985 ? 26 : v * 9;
  }
  ctx.putImageData(image, 0, 0);
  ctx.lineCap = 'round';
  for (let i = 0; i < 46; i++) {
    const x = rand() * size, y = rand() * size, angle = rand() * Math.PI, length = 3 + rand() * 9;
    ctx.strokeStyle = `rgba(${rand() > 0.5 ? '255,255,250' : '120,100,60'},${0.08 + rand() * 0.1})`;
    ctx.lineWidth = 0.6;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.quadraticCurveTo(x + Math.cos(angle) * length * 0.5 + gaussian(rand), y + Math.sin(angle) * length * 0.5 + gaussian(rand), x + Math.cos(angle) * length, y + Math.sin(angle) * length);
    ctx.stroke();
  }
  return canvas.toDataURL('image/png');
}

export function stainSprite(seed, kind, inkIndex = seed, size = 320) {
  const rand = rng(seed), [canvas, ctx] = canvasOf(size, size, true), ink = INKS[inkIndex % INKS.length], c = size / 2;
  if (kind === 'ring') ring(ctx, c, c, size * 0.36, ink, rand, 0.55);
  else {
    bloom(ctx, c, c, size * 0.26, ink, rand, 0.6);
    if (rand() > 0.4) bloom(ctx, c + gaussian(rand) * size * 0.14, c + gaussian(rand) * size * 0.14, size * 0.1, INKS[(inkIndex + 1) % 4], rand, 0.5);
  }
  return canvas.toDataURL('image/png');
}

// The page behind everything: a few big faint washes near the edges and one cup ring.
export function backdrop(width, height, seed) {
  const rand = rng(seed), [canvas, ctx] = canvasOf(width, height, true);
  const spots = [[0.08, 0.12], [0.94, 0.18], [0.88, 0.9], [0.18, 0.86], [0.55, 0.04]];
  spots.forEach(([x, y], i) => bloom(ctx, width * (x + gaussian(rand) * 0.03), height * (y + gaussian(rand) * 0.03), Math.min(width, height) * (0.12 + rand() * 0.1), INKS[[0, 3, 0, 3, 2][i]], rand, 0.75));
  ring(ctx, width * (0.7 + rand() * 0.2), height * (0.55 + rand() * 0.3), Math.min(width, height) * 0.07, INKS[5], rand, 0.5);
  return canvas.toDataURL('image/png');
}

export function installPaper(root = document.documentElement, seed = seedFrom('atlas-paper')) {
  if (typeof document === 'undefined' || !document.createElement('canvas').getContext) return () => {};
  const set = (name, url) => root.style.setProperty(name, `url("${url}")`);
  set('--paper-grain', grainTile(seed));
  // Mostly ochre, gold and tea, so the paper stays cream and gold; sage only once.
  [['bloom', 0], ['ring', 2], ['bloom', 1], ['bloom', 4], ['ring', 5], ['bloom', 3]].forEach(([kind, ink], i) => set(`--stain-${i + 1}`, stainSprite(seed + i * 7919, kind, ink)));
  let timer = 0, painted = '';
  const paintBackdrop = () => {
    // Rounded so small resizes keep the same picture; capped to keep the data URL small.
    const width = Math.min(2200, Math.ceil(window.innerWidth / 200) * 200), height = Math.min(1600, Math.ceil(window.innerHeight / 200) * 200);
    if (`${width}x${height}` === painted) return;
    painted = `${width}x${height}`;
    set('--paper-backdrop', backdrop(width, height, seed));
  };
  const onResize = () => { clearTimeout(timer); timer = setTimeout(paintBackdrop, 300); };
  paintBackdrop();
  window.addEventListener('resize', onResize);
  return () => window.removeEventListener('resize', onResize);
}
