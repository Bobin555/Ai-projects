// Find which way is up in a raw splat scan and level it: up = +Y, floor at y = 0, floor centred on x = z = 0.
import * as pc from 'playcanvas';

const AXES = { x: [1, 0, 0], y: [0, 1, 0], z: [0, 0, 1] };
const CLUSTER_COS = Math.cos((10 * Math.PI) / 180);
const FACING_UP_COS = Math.cos((20 * Math.PI) / 180);
const BAND = 1.2;   // metres above the floor where furniture makes the floor side heavier
const SAMPLE = 4000;

const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const norm = (a) => { const l = Math.hypot(...a) || 1; return a.map((v) => v / l); };

// Normal (shortest axis) and flat area of each sampled flat splat, in scan coordinates.
function flatSplats(splat) {
  const { props, count, data } = splat;
  const col = (n) => props.indexOf(n);
  const si = ['scale_0', 'scale_1', 'scale_2'].map(col);
  const ri = ['rot_0', 'rot_1', 'rot_2', 'rot_3'].map(col);
  if ([...si, ...ri].some((k) => k < 0)) return null;
  const stride = props.length;
  const step = Math.max(1, Math.floor(count / SAMPLE));
  const q = new pc.Quat();
  const v = new pc.Vec3();
  const out = [];
  for (let n = 0; n < count; n += step) {
    const s = si.map((k) => Math.exp(data[n * stride + k]));
    const order = [0, 1, 2].sort((a, b) => s[a] - s[b]);
    if (s[order[0]] / s[order[1]] >= 0.3) continue; // not flat
    const [w, x, y, z] = ri.map((k) => data[n * stride + k]);
    q.set(x, y, z, w).normalize();
    const axis = [0, 0, 0];
    axis[order[0]] = 1;
    q.transformVector(v.set(...axis), v);
    out.push({ n, normal: [v.x, v.y, v.z], area: s[order[1]] * s[order[2]] });
  }
  return out;
}

// Group normals that point the same way (ignoring sign), weighted by area. Biggest group = up.
function dominantNormal(flats) {
  const clusters = [];
  for (const f of [...flats].sort((a, b) => b.area - a.area)) {
    let best = null;
    for (const c of clusters) {
      const d = dot(norm(c.sum), f.normal);
      if (Math.abs(d) >= CLUSTER_COS) { best = { c, sign: Math.sign(d) }; break; }
    }
    if (!best) { clusters.push({ sum: f.normal.map((v) => v * f.area), weight: f.area }); continue; }
    best.c.sum = best.c.sum.map((v, k) => v + f.normal[k] * f.area * best.sign);
    best.c.weight += f.area;
  }
  const total = clusters.reduce((s, c) => s + c.weight, 0);
  return clusters
    .sort((a, b) => b.weight - a.weight)
    .slice(0, 3)
    .map((c) => ({ direction: norm(c.sum), share: c.weight / total }));
}

function percentile(sorted, p) {
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.floor(p * (sorted.length - 1))))];
}

// up: 'x' | 'y' | 'z' forces a scan axis; a number (1-3) picks that candidate from a previous run's report.
export function levelSplat(splat, { up: upAxis, flip = false } = {}) {
  const { props, count, data } = splat;
  const stride = props.length;
  const [xi, yi, zi] = ['x', 'y', 'z'].map((p) => props.indexOf(p));
  const pos = (n) => [data[n * stride + xi], data[n * stride + yi], data[n * stride + zi]];

  const flats = flatSplats(splat);
  const candidates = flats?.length ? dominantNormal(flats) : [];
  const forcedAxis = typeof upAxis === 'string';
  let up;
  let confidence = 0;
  if (forcedAxis) {
    up = AXES[upAxis];
  } else if (typeof upAxis === 'number') {
    if (!candidates[upAxis - 1]) throw new Error(`There is no up candidate ${upAxis} (found ${candidates.length})`);
    up = candidates[upAxis - 1].direction;
    confidence = candidates[upAxis - 1].share;
  } else {
    up = candidates[0]?.direction ?? AXES.y;
    confidence = candidates[0]?.share ?? 0;
  }
  // Close call: the runner-up has nearly as much flat area (e.g. a corridor's long walls vs its floor).
  const ambiguous = candidates.length > 1 && candidates[1].share >= 0.6 * candidates[0].share;

  // Heights along up. The floor is the end with more splats in its first BAND metres.
  const heights = new Float64Array(count);
  for (let n = 0; n < count; n++) heights[n] = dot(pos(n), up);
  const sorted = Float64Array.from(heights).sort();
  const lo = percentile(sorted, 0.01);
  const hi = percentile(sorted, 0.99);
  let nearLo = 0;
  let nearHi = 0;
  for (const h of heights) { if (h >= lo && h <= lo + BAND) nearLo++; if (h <= hi && h >= hi - BAND) nearHi++; }
  if (!forcedAxis && nearHi > nearLo) up = up.map((v) => -v);
  if (flip) up = up.map((v) => -v);
  for (let n = 0; n < count; n++) heights[n] = dot(pos(n), up);
  const sorted2 = Float64Array.from(heights).sort();
  const bottom = percentile(sorted2, 0.01);
  const top = percentile(sorted2, 0.99);

  // Floor height: most common height of up-facing flat splats in the lowest third.
  let floorH = bottom;
  const third = bottom + (top - bottom) / 3;
  const bins = new Map();
  for (const f of flats ?? []) {
    if (Math.abs(dot(f.normal, up)) < FACING_UP_COS) continue;
    const h = heights[f.n];
    if (h > third) continue;
    const b = Math.round(h / 0.05);
    bins.set(b, (bins.get(b) ?? 0) + 1);
  }
  if (bins.size) floorH = [...bins.entries()].reduce((a, b) => (b[1] > a[1] ? b : a))[0] * 0.05;
  if (!flats?.length) {
    // No orientation data: the floor is the densest 5 cm layer in the lowest third.
    const layer = new Map();
    for (const h of heights) if (h <= third) { const b = Math.round(h / 0.05); layer.set(b, (layer.get(b) ?? 0) + 1); }
    if (layer.size) floorH = [...layer.entries()].reduce((a, b) => (b[1] > a[1] ? b : a))[0] * 0.05;
  }

  // Rotation taking up to +Y (shortest arc; 180 degrees about X if up points straight down).
  const q = new pc.Quat();
  const d = up[1];
  if (d < -0.999999) q.setFromAxisAngle(pc.Vec3.RIGHT, 180);
  else {
    const axis = new pc.Vec3(-up[2], 0, up[0]); // up x Y
    if (axis.length() < 1e-9) q.set(0, 0, 0, 1);
    else q.setFromAxisAngle(axis.normalize(), (Math.acos(Math.min(1, d)) * 180) / Math.PI);
  }

  const positions = new Float32Array(count * 3);
  const v = new pc.Vec3();
  let sx = 0; let sz = 0; let nFloor = 0;
  for (let n = 0; n < count; n++) {
    q.transformVector(v.set(...pos(n)), v);
    positions.set([v.x, v.y - floorH, v.z], n * 3);
    if (Math.abs(v.y - floorH) <= 0.15) { sx += v.x; sz += v.z; nFloor++; }
  }
  const cx = nFloor ? sx / nFloor : 0;
  const cz = nFloor ? sz / nFloor : 0;
  for (let n = 0; n < count; n++) { positions[n * 3] -= cx; positions[n * 3 + 2] -= cz; }

  const levelledY = Float64Array.from({ length: count }, (_, n) => positions[n * 3 + 1]).sort();
  const roomHeight = percentile(levelledY, 0.99);

  const e = q.getEulerAngles();
  return { rotation: [e.x, e.y, e.z], position: [-cx, -floorH, -cz], positions, confidence, upAxisScan: up, candidates, ambiguous, roomHeight };
}
