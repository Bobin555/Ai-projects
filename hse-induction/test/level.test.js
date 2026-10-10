import { describe, it, expect } from 'vitest';
import { levelSplat } from '../scripts/level.js';
import { makeRoom, stripProps } from './helpers/fakeRoom.js';

const ys = (positions, kinds, kind) => kinds.flatMap((k, n) => (k === kind ? [positions[n * 3 + 1]] : []));
const mean = (a) => a.reduce((s, v) => s + v, 0) / a.length;
const maxAbs = (a) => Math.max(...a.map(Math.abs));

function expectLevel({ positions }, kinds, tol = 0.05) {
  expect(maxAbs(ys(positions, kinds, 'floor'))).toBeLessThan(tol);
  expect(mean(ys(positions, kinds, 'ceiling'))).toBeCloseTo(3, 1);
}

describe('levelSplat', () => {
  it('leaves a Y-up room upright with the floor at 0', () => {
    const { splat, kinds } = makeRoom();
    const r = levelSplat(splat);
    expectLevel(r, kinds);
    expect(r.confidence).toBeGreaterThan(0.4);
  });
  it('turns a Z-up scan upright', () => {
    const { splat, kinds } = makeRoom({ rotation: [90, 0, 0] });
    expectLevel(levelSplat(splat), kinds);
  });
  it('turns an upside-down (-Z up) scan upright', () => {
    const { splat, kinds } = makeRoom({ rotation: [-90, 0, 0] });
    expectLevel(levelSplat(splat), kinds);
  });
  it('levels a scan tilted 20 degrees to within 2 degrees', () => {
    const { splat, kinds } = makeRoom({ rotation: [20, 0, 0] });
    expectLevel(levelSplat(splat), kinds, 5 * Math.tan((2 * Math.PI) / 180));
  });
  it('flip turns the result over', () => {
    const { splat, kinds } = makeRoom();
    const r = levelSplat(splat, { flip: true });
    expect(maxAbs(ys(r.positions, kinds, 'ceiling'))).toBeLessThan(0.05);
    expect(mean(ys(r.positions, kinds, 'floor'))).toBeCloseTo(3, 1);
  });
  it('up forces the scan axis that points up', () => {
    const { splat, kinds } = makeRoom({ rotation: [90, 0, 0] });
    expectLevel(levelSplat(splat, { up: 'z' }), kinds);
  });
  it('falls back to the given up axis when the PLY has no scale or rotation', () => {
    const { splat, kinds } = makeRoom();
    const r = levelSplat(stripProps(splat, ['x', 'y', 'z']));
    expect(r.confidence).toBe(0);
    expect(maxAbs(ys(r.positions, kinds, 'floor'))).toBeLessThan(0.05);
  });
  it('centres the floor on x = z = 0', () => {
    const { splat, kinds } = makeRoom({ offset: [50, 7, 20] });
    const { positions } = levelSplat(splat);
    const floor = kinds.flatMap((k, n) => (k === 'floor' ? [n] : []));
    expect(Math.abs(mean(floor.map((n) => positions[n * 3])))).toBeLessThan(0.1);
    expect(Math.abs(mean(floor.map((n) => positions[n * 3 + 2])))).toBeLessThan(0.1);
  });
  it('returns a rotation and position that reproduce the levelled points in PlayCanvas', async () => {
    const pc = await import('playcanvas');
    const { splat } = makeRoom({ rotation: [90, 30, 0], offset: [3, 4, 5] });
    const r = levelSplat(splat);
    const q = new pc.Quat().setFromEulerAngles(...r.rotation);
    const v = q.transformVector(new pc.Vec3(splat.data[0], splat.data[1], splat.data[2])).add(new pc.Vec3(...r.position));
    expect(v.x).toBeCloseTo(r.positions[0], 3);
    expect(v.y).toBeCloseTo(r.positions[1], 3);
    expect(v.z).toBeCloseTo(r.positions[2], 3);
  });
});

describe('levelSplat: ambiguity and size', () => {
  // A 2 m wide, 20 m long, 2.7 m high corridor: its two long walls have more flat area than floor + ceiling.
  it('reports the room height', () => {
    const { splat } = makeRoom();
    expect(levelSplat(splat).roomHeight).toBeCloseTo(3, 0);
  });
  it('lists candidate up directions, biggest first, and flags a close call', async () => {
    const { makeCorridor } = await import('./helpers/fakeRoom.js');
    const { splat, kinds } = makeCorridor({ rotation: [90, 0, 0] });
    const r = levelSplat(splat);
    expect(r.candidates.length).toBeGreaterThanOrEqual(2);
    expect(r.candidates[0].share).toBeGreaterThanOrEqual(r.candidates[1].share);
    expect(r.ambiguous).toBe(true);
    // Picking the floor/ceiling candidate by number levels it properly.
    const pick = r.candidates.findIndex((c) => Math.abs(c.direction[2]) > 0.9) + 1;
    const fixed = levelSplat(splat, { up: pick });
    const floorYs = kinds.flatMap((k, n) => (k === 'floor' ? [fixed.positions[n * 3 + 1]] : []));
    expect(Math.max(...floorYs.map(Math.abs))).toBeLessThan(0.05);
  });
  it('is not ambiguous for an ordinary room', () => {
    const { splat } = makeRoom({ rotation: [90, 0, 0] });
    expect(levelSplat(splat).ambiguous).toBe(false);
  });
});
