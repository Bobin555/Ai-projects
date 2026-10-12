import { describe, it, expect } from 'vitest';
import { buildColliders, pickStart } from '../scripts/colliders.js';
import { overlapIndex } from '../src/collision.js';
import { makeRoom } from './helpers/fakeRoom.js';

const { splat, kinds } = makeRoom({ doorway: true, step: 0.1 });
const positions = new Float32Array(splat.count * 3);
for (let n = 0; n < splat.count; n++) positions.set(splat.data.subarray(n * splat.props.length, n * splat.props.length + 3), n * 3);

const inside = (p, b, tol = 1e-6) => [0, 1, 2].every((k) => Math.abs(p[k] - b.position[k]) <= b.size[k] / 2 + tol);
// Wall boxes are inset 0.1 m so doorways stay open; points at a box's very edge may sit just outside.
const nearAny = (p, boxes) => boxes.some((b) => inside(p, b, 0.11));
const inAny = (p, boxes) => boxes.some((b) => inside(p, b));
const result = buildColliders(positions);
const { colliders } = result;

describe('buildColliders', () => {
  it('covers every wall point at body height', () => {
    const missed = kinds.flatMap((k, n) => {
      const p = [positions[n * 3], positions[n * 3 + 1], positions[n * 3 + 2]];
      return k === 'wall' && p[1] >= 0.3 && p[1] <= 1.8 && !nearAny(p, colliders) ? [p] : [];
    });
    expect(missed).toEqual([]);
  });
  it('keeps a 1 m doorway open', () => {
    expect(inAny([0, 1, -5], colliders)).toBe(false);
    expect(overlapIndex([0, 0, -5], colliders)).toBe(-1);
  });
  it('puts a floor under the room with its top at y = 0', () => {
    const floor = colliders.find((b) => inside([2.5, -0.05, -2.5], b));
    expect(floor).toBeDefined();
    expect(floor.position[1] + floor.size[1] / 2).toBeCloseTo(0, 6);
  });
  it('merges a straight wall into at most 2 boxes', () => {
    const south = colliders.filter((b) => b.position[1] > 0 && inside([b.position[0], 1, 5.1], b));
    expect(south.length).toBeGreaterThan(0);
    expect(south.length).toBeLessThanOrEqual(2);
  });
  it('makes the table solid', () => {
    expect(inAny([1.5, 0.5, 1.5], colliders)).toBe(true);
  });
  it('grows the grid when there would be too many boxes', () => {
    const small = buildColliders(positions, { maxBoxes: 6 });
    expect(small.colliders.length).toBeLessThanOrEqual(6);
    expect(small.cell).toBeGreaterThan(0.25);
  });
});

describe('pickStart', () => {
  const start = pickStart(result);
  it('starts inside the room, on the floor, clear of every box', () => {
    const [x, y, z] = start.position;
    expect(Math.abs(x)).toBeLessThan(5);
    expect(Math.abs(z)).toBeLessThan(5);
    expect(y).toBe(0);
    expect(overlapIndex(start.position, colliders)).toBe(-1);
  });
  it('keeps at least 0.6 m from walls and furniture', () => {
    const solid = colliders.filter((b) => b.position[1] > 0);
    const gap = Math.min(...solid.map((b) => {
      const dx = Math.max(0, Math.abs(start.position[0] - b.position[0]) - b.size[0] / 2);
      const dz = Math.max(0, Math.abs(start.position[2] - b.position[2]) - b.size[2] / 2);
      return Math.hypot(dx, dz);
    }));
    expect(gap).toBeGreaterThanOrEqual(0.6);
  });
  it('faces a direction', () => {
    expect(Number.isFinite(start.yaw)).toBe(true);
  });
});

describe('doorways that do not line up with the grid', () => {
  // A wall at z = -3 along x in [-4, 4], with an 0.85 m gap centred at various offsets.
  const wallWithGap = (centre, width = 0.85) => {
    const pts = [];
    for (let x = -4; x <= 4; x += 0.05) for (let y = 0; y <= 2.5; y += 0.1) for (let z = -5; z <= 5; z += 0.25) {
      if (y === 0) pts.push(x, 0, z); // floor
    }
    for (let x = -4; x <= 4; x += 0.02) {
      if (Math.abs(x - centre) < width / 2) continue;
      for (let y = 0.3; y <= 1.8; y += 0.05) pts.push(x, y, -3);
    }
    return Float32Array.from(pts);
  };
  for (const offset of [0, 0.05, 0.12, 0.2]) {
    it(`lets the player through an 0.85 m doorway at offset ${offset}`, () => {
      const { colliders } = buildColliders(wallWithGap(offset));
      expect(overlapIndex([offset, 0, -3], colliders)).toBe(-1);
      expect(overlapIndex([offset + 1, 0, -3], colliders)).toBeGreaterThanOrEqual(0); // the wall itself still blocks
    });
  }
  it('keeps walls solid after growing the grid', () => {
    const small = buildColliders(positions, { maxBoxes: 6 });
    expect(overlapIndex([2, 0, -5], small.colliders)).toBeGreaterThanOrEqual(0);
  });
});

describe('real scans with floating specks at body height', () => {
  // Modelled on a real reception scan's diagnosis: about 11 specks per 0.25 m cell at body height (above the old
  // fixed threshold of 8) and wall cells with 100+ splats.
  const dense = makeRoom({ doorway: true, step: 0.05 }).splat;
  const base = [];
  for (let n = 0; n < dense.count; n++) base.push(...dense.data.subarray(n * dense.props.length, n * dense.props.length + 3));
  const specks = [];
  let seed = 1;
  const rand = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
  for (let i = 0; i < 1600 * 11; i++) specks.push(rand() * 10 - 5, 0.3 + rand() * 1.5, rand() * 10 - 5);
  const noisy = Float32Array.from([...base, ...specks]);
  const r = buildColliders(noisy);

  it('still finds open floor to start on', () => {
    const start = pickStart(r);
    expect(start).not.toBeNull();
    expect(overlapIndex(start.position, r.colliders)).toBe(-1);
  });
  it('keeps real walls solid', () => {
    expect(overlapIndex([2, 0, -5], r.colliders)).toBeGreaterThanOrEqual(0);
    expect(overlapIndex([-5, 0, 2], r.colliders)).toBeGreaterThanOrEqual(0);
  });
  it('does not turn most of the floor into walls', () => {
    expect(r.solidCells.size).toBeLessThan(r.floorCells.size * 0.3);
  });
});
