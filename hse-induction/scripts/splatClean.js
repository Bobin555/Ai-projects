// Clean a 3D Gaussian Splat .ply: drop faint splats, huge blobs, far-away junk and floaters.
// Pure functions over { props: string[], count: number, data: Float32Array (interleaved rows) }.

export function parsePly(buf) {
  const end = buf.indexOf('end_header\n');
  if (end < 0) throw new Error('Not a PLY file (no end_header)');
  const header = buf.subarray(0, end).toString('latin1').split('\n');
  if (!header.includes('format binary_little_endian 1.0')) {
    throw new Error('Only binary_little_endian PLY files are supported');
  }
  let count = 0;
  const props = [];
  let inVertex = false;
  for (const line of header) {
    const parts = line.trim().split(/\s+/);
    if (parts[0] === 'element') { inVertex = parts[1] === 'vertex'; if (inVertex) count = Number(parts[2]); else if (Number(parts[2]) > 0) throw new Error(`Unsupported element "${parts[1]}"`); }
    if (parts[0] === 'property' && inVertex) {
      if (parts[1] !== 'float' && parts[1] !== 'float32') throw new Error(`Only float properties are supported (got ${parts[1]} ${parts[2]})`);
      props.push(parts[2]);
    }
  }
  const start = end + 'end_header\n'.length;
  const bytes = count * props.length * 4;
  if (buf.length - start < bytes) throw new Error('PLY file is truncated');
  const data = new Float32Array(count * props.length);
  // Copy so the Float32Array is aligned regardless of header length.
  new Uint8Array(data.buffer).set(buf.subarray(start, start + bytes));
  return { props, count, data };
}

export function writePly({ props, count, data }) {
  const header = ['ply', 'format binary_little_endian 1.0', `element vertex ${count}`, ...props.map((p) => `property float ${p}`), 'end_header', ''].join('\n');
  return Buffer.concat([Buffer.from(header, 'latin1'), Buffer.from(data.buffer, data.byteOffset, count * props.length * 4)]);
}

const sigmoid = (x) => 1 / (1 + Math.exp(-x));

function median(values) {
  if (!values.length) return 0;
  const s = Float64Array.from(values).sort();
  return s[Math.floor(s.length / 2)];
}

function percentile(sorted, p) {
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.floor(p * (sorted.length - 1))))];
}

// Numeric grid key; cell indices are clamped to ±32767 so the key stays an exact integer.
const cellKey = (ix, iy, iz) => ((ix + 32768) * 65536 + (iy + 32768)) * 65536 + (iz + 32768);
const clampCell = (v) => Math.max(-32767, Math.min(32767, v));

function neighbourCounter(pos, idx, h) {
  const cells = new Map();
  const cellOf = (n) => [0, 1, 2].map((k) => clampCell(Math.floor(pos[n * 3 + k] / h)));
  for (const n of idx) {
    const [x, y, z] = cellOf(n);
    const key = cellKey(x, y, z);
    cells.set(key, (cells.get(key) ?? 0) + 1);
  }
  return (n) => {
    const [x, y, z] = cellOf(n);
    let total = -1; // don't count the splat itself
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) for (let dz = -1; dz <= 1; dz++) {
      total += cells.get(cellKey(x + dx, y + dy, z + dz)) ?? 0;
    }
    return total;
  };
}

export const DEFAULTS = {
  minOpacity: 0.05,     // splats fainter than this are haze
  hugeFactor: 20,       // splats this many times bigger than the typical one are blobs
  trimPercent: 0.01,    // ignore the outermost 1% on each axis when finding the scan's extent...
  trimMargin: 0.25,     // ...then keep a margin of 25% of the largest extent around it
  targetNeighbours: 30, // grid size is tuned so a typical splat has about this many neighbours
  minNeighbours: 3,     // splats with fewer neighbours than this are floaters
  box: null,            // [minX, minY, minZ, maxX, maxY, maxZ] overrides the automatic trim
};

export function cleanSplat(splat, options = {}) {
  const o = { ...DEFAULTS, ...options };
  const { props, count, data } = splat;
  const stride = props.length;
  const col = (name) => props.indexOf(name);
  const [xi, yi, zi] = ['x', 'y', 'z'].map(col);
  if (xi < 0 || yi < 0 || zi < 0) throw new Error('PLY has no x/y/z properties');
  const oi = col('opacity');
  const si = ['scale_0', 'scale_1', 'scale_2'].map(col);

  const pos = new Float64Array(count * 3);
  for (let n = 0; n < count; n++) {
    pos[n * 3] = data[n * stride + xi];
    pos[n * 3 + 1] = data[n * stride + yi];
    pos[n * 3 + 2] = data[n * stride + zi];
  }
  const removed = { faint: 0, huge: 0, outside: 0, floaters: 0 };
  let keep = Array.from({ length: count }, (_, n) => n);

  // 1. Faint splats.
  if (oi >= 0) {
    const before = keep.length;
    keep = keep.filter((n) => sigmoid(data[n * stride + oi]) >= o.minOpacity);
    removed.faint = before - keep.length;
  }

  // 2. Huge blobs, judged against the typical splat size.
  if (si.every((k) => k >= 0)) {
    const size = (n) => Math.exp(Math.max(...si.map((k) => data[n * stride + k])));
    const typical = median(keep.map(size));
    const before = keep.length;
    keep = keep.filter((n) => size(n) <= typical * o.hugeFactor);
    removed.huge = before - keep.length;
  }

  // 3. Far-away junk: outside --box, or outside the trimmed extent plus a margin.
  {
    let lo;
    let hi;
    if (o.box) {
      lo = o.box.slice(0, 3);
      hi = o.box.slice(3, 6);
    } else if (keep.length) {
      const ranges = [0, 1, 2].map((k) => {
        const s = Float64Array.from(keep, (n) => pos[n * 3 + k]).sort();
        return [percentile(s, o.trimPercent), percentile(s, 1 - o.trimPercent)];
      });
      const margin = o.trimMargin * Math.max(...ranges.map(([a, b]) => b - a));
      lo = ranges.map(([a]) => a - margin);
      hi = ranges.map(([, b]) => b + margin);
    }
    if (lo) {
      const before = keep.length;
      keep = keep.filter((n) => [0, 1, 2].every((k) => pos[n * 3 + k] >= lo[k] && pos[n * 3 + k] <= hi[k]));
      removed.outside = before - keep.length;
    }
  }

  // 4. Floaters: tune a grid so a typical splat has ~targetNeighbours, then drop the isolated ones.
  if (keep.length > o.targetNeighbours * 2) {
    const extent = Math.max(...[0, 1, 2].map((k) => {
      let a = Infinity; let b = -Infinity;
      for (const n of keep) { a = Math.min(a, pos[n * 3 + k]); b = Math.max(b, pos[n * 3 + k]); }
      return b - a;
    })) || 1;
    const step = Math.max(1, Math.floor(keep.length / 20000));
    const sample = keep.filter((_, i) => i % step === 0);
    let lo = Math.log(extent / 4000);
    let hi = Math.log(extent / 2);
    for (let i = 0; i < 14; i++) {
      const mid = (lo + hi) / 2;
      const count27 = neighbourCounter(pos, keep, Math.exp(mid));
      if (median(sample.map(count27)) < o.targetNeighbours) lo = mid; else hi = mid;
    }
    const count27 = neighbourCounter(pos, keep, Math.exp(hi));
    const before = keep.length;
    keep = keep.filter((n) => count27(n) >= o.minNeighbours);
    removed.floaters = before - keep.length;
  }

  const out = new Float32Array(keep.length * stride);
  keep.forEach((n, i) => out.set(data.subarray(n * stride, (n + 1) * stride), i * stride));
  return {
    splat: { props, count: keep.length, data: out },
    stats: { before: count, after: keep.length, removed },
  };
}
