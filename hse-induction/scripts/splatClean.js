// Clean a 3D Gaussian Splat .ply: drop invisible splats, far-away junk and huge blobs.
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

function percentile(sorted, p) {
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.floor(p * (sorted.length - 1))))];
}

export const DEFAULTS = {
  minOpacity: 0.005,    // same threshold 3DGS training prunes at; anything fainter is invisible
  hugeFraction: 0.1,    // splats wider than 10% of the whole scan are sky/reflection blobs
  trimPercent: 0.01,    // ignore the outermost 1% on each axis when finding the scan's extent...
  trimMargin: 0.25,     // ...then keep a margin of 25% of the largest extent around it
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
  const removed = { faint: 0, huge: 0, outside: 0 };
  let extent = 0;
  let keep = Array.from({ length: count }, (_, n) => n);

  // 1. Faint splats.
  if (oi >= 0) {
    const before = keep.length;
    keep = keep.filter((n) => sigmoid(data[n * stride + oi]) >= o.minOpacity);
    removed.faint = before - keep.length;
  }

  // 2. Far-away junk: outside --box, or outside the trimmed extent plus a margin.
  {
    let lo;
    let hi;
    if (o.box) {
      lo = o.box.slice(0, 3);
      hi = o.box.slice(3, 6);
      extent = Math.max(...[0, 1, 2].map((k) => hi[k] - lo[k]));
    } else if (keep.length) {
      const ranges = [0, 1, 2].map((k) => {
        const s = Float64Array.from(keep, (n) => pos[n * 3 + k]).sort();
        return [percentile(s, o.trimPercent), percentile(s, 1 - o.trimPercent)];
      });
      extent = Math.max(...ranges.map(([a, b]) => b - a));
      const margin = o.trimMargin * extent;
      lo = ranges.map(([a]) => a - margin);
      hi = ranges.map(([, b]) => b + margin);
    }
    if (lo) {
      const before = keep.length;
      keep = keep.filter((n) => [0, 1, 2].every((k) => pos[n * 3 + k] >= lo[k] && pos[n * 3 + k] <= hi[k]));
      removed.outside = before - keep.length;
    }
  }

  // 3. Huge blobs, judged against the size of the whole scan (big flat wall/ceiling splats are fine).
  if (si.every((k) => k >= 0) && extent > 0) {
    const limit = extent * o.hugeFraction;
    const before = keep.length;
    keep = keep.filter((n) => Math.exp(Math.max(...si.map((k) => data[n * stride + k]))) <= limit);
    removed.huge = before - keep.length;
  }

  const out = new Float32Array(keep.length * stride);
  keep.forEach((n, i) => out.set(data.subarray(n * stride, (n + 1) * stride), i * stride));
  return {
    splat: { props, count: keep.length, data: out },
    stats: { before: count, after: keep.length, removed },
  };
}
