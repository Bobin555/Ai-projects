import { describe, it, expect } from 'vitest';
import { parsePly, writePly, cleanSplat } from '../scripts/splatClean.js';

const PROPS = ['x', 'y', 'z', 'f_dc_0', 'f_dc_1', 'f_dc_2', 'opacity', 'scale_0', 'scale_1', 'scale_2', 'rot_0', 'rot_1', 'rot_2', 'rot_3'];
const logit = (p) => Math.log(p / (1 - p));

// A dense 10 x 10 m floor of solid, small splats on a 0.25 m grid, plus extras.
function makeSplat(extras = []) {
  const rows = [];
  for (let i = 0; i < 40; i++) for (let j = 0; j < 40; j++) rows.push({ x: i * 0.25 - 5, y: 0, z: j * 0.25 - 5 });
  rows.push(...extras);
  const data = new Float32Array(rows.length * PROPS.length);
  rows.forEach((r, n) => {
    const v = { f_dc_0: 0.5, f_dc_1: 0.5, f_dc_2: 0.5, opacity: logit(0.9), scale_0: Math.log(0.05), scale_1: Math.log(0.05), scale_2: Math.log(0.05), rot_0: 1, rot_1: 0, rot_2: 0, rot_3: 0, ...r };
    PROPS.forEach((p, k) => { data[n * PROPS.length + k] = v[p]; });
  });
  return { props: PROPS, count: rows.length, data };
}
const FLOOR = 1600;
const positions = (s) => Array.from({ length: s.count }, (_, n) => [0, 1, 2].map((k) => s.data[n * s.props.length + k]));

describe('parsePly / writePly', () => {
  it('round-trips a binary float PLY', () => {
    const s = makeSplat();
    const back = parsePly(writePly(s));
    expect(back.props).toEqual(PROPS);
    expect(back.count).toBe(FLOOR);
    expect(Array.from(back.data.slice(0, 14))).toEqual(Array.from(s.data.slice(0, 14)));
  });
  it('rejects a PLY with non-float properties', () => {
    const bad = Buffer.from('ply\nformat binary_little_endian 1.0\nelement vertex 1\nproperty uchar red\nend_header\n\x01', 'latin1');
    expect(() => parsePly(bad)).toThrow(/float/);
  });
  it('rejects an ASCII PLY', () => {
    const bad = Buffer.from('ply\nformat ascii 1.0\nelement vertex 0\nproperty float x\nend_header\n', 'latin1');
    expect(() => parsePly(bad)).toThrow(/binary_little_endian/);
  });
});

describe('cleanSplat', () => {
  it('keeps a clean floor untouched', () => {
    const { splat, stats } = cleanSplat(makeSplat());
    expect(splat.count).toBe(FLOOR);
    expect(stats.removed).toEqual({ faint: 0, huge: 0, outside: 0 });
  });
  it('removes only splats fainter than the 3DGS training prune threshold', () => {
    const { splat, stats } = cleanSplat(makeSplat([
      { x: 0, y: 0.1, z: 0, opacity: logit(0.001) },
      { x: 0, y: 0.1, z: 0.1, opacity: logit(0.02) }, // faint but real: thin layers build up colour
    ]));
    expect(splat.count).toBe(FLOOR + 1);
    expect(stats.removed.faint).toBe(1);
  });
  it('keeps large flat splats that cover walls and ceilings', () => {
    const wall = Math.log(0.6); // 12x the typical 5 cm splat, but small next to a 10 m room
    const { splat, stats } = cleanSplat(makeSplat([{ x: 0, y: 2, z: 0, scale_0: wall, scale_1: wall, scale_2: Math.log(0.01) }]));
    expect(splat.count).toBe(FLOOR + 1);
    expect(stats.removed.huge).toBe(0);
  });
  it('removes blobs bigger than a tenth of the whole scan', () => {
    const big = Math.log(3); // 3 m blob in a 10 m scan
    const { splat, stats } = cleanSplat(makeSplat([{ x: 0, y: 2, z: 0, scale_0: big, scale_1: big, scale_2: big }]));
    expect(splat.count).toBe(FLOOR);
    expect(stats.removed.huge).toBe(1);
  });
  it('trims far-away junk outside the main scan', () => {
    const { splat, stats } = cleanSplat(makeSplat([{ x: 500, y: 0, z: 0 }]));
    expect(splat.count).toBe(FLOOR);
    expect(stats.removed.outside).toBe(1);
  });
  it('leaves floaters inside the scan alone (that is SplatTransform\'s --floaters job)', () => {
    const { splat } = cleanSplat(makeSplat([{ x: 1, y: 2, z: 1 }]));
    expect(splat.count).toBe(FLOOR + 1);
  });
  it('keeps only splats inside --box when one is given', () => {
    const { splat, stats } = cleanSplat(makeSplat(), { box: [-1, -1, -1, 1, 1, 1] });
    expect(positions(splat).every(([x, , z]) => x >= -1 && x <= 1 && z >= -1 && z <= 1)).toBe(true);
    expect(stats.removed.outside).toBe(FLOOR - splat.count);
    expect(splat.count).toBeGreaterThan(0);
  });
  it('reports before and after counts', () => {
    const { stats } = cleanSplat(makeSplat([{ x: 0, y: 0.1, z: 0, opacity: logit(0.001) }]));
    expect(stats.before).toBe(FLOOR + 1);
    expect(stats.after).toBe(FLOOR);
  });
});
