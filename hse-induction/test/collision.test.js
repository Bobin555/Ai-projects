import { describe, it, expect } from 'vitest';
import { moveWithCollision } from '../src/collision.js';

const floor = { position: [0, -0.5, 0], size: [40, 1, 40] }; // top at y=0
const R = 0.3;

describe('moveWithCollision', () => {
  it('stays on the floor when standing still', () => {
    const r = moveWithCollision([0, 0, 0], [0, 0, 0], 0.016, [floor]);
    expect(r.pos[1]).toBeCloseTo(0);
  });

  it('stops at a wall and keeps sliding along it', () => {
    const wall = { position: [2, 1, 0], size: [0.2, 2, 10] }; // minX = 1.9
    let pos = [1, 0, 0];
    for (let i = 0; i < 60; i++) pos = moveWithCollision(pos, [3, 0, 1], 0.016, [floor, wall]).pos;
    expect(pos[0]).toBeCloseTo(1.9 - R, 3);
    expect(pos[2]).toBeGreaterThan(0.9);
  });

  it('lands on the floor when falling', () => {
    let s = { pos: [0, 5, 0], vel: [0, 0, 0] };
    for (let i = 0; i < 200; i++) {
      s.vel[1] -= 9.8 * 0.016;
      s = moveWithCollision(s.pos, s.vel, 0.016, [floor]);
    }
    expect(s.pos[1]).toBeCloseTo(0);
    expect(s.vel[1]).toBe(0);
  });

  it('clamps a huge dt so the player cannot tunnel through a thin wall', () => {
    const wall = { position: [1.1, 1, 0], size: [0.2, 2, 10] }; // 1 m ahead
    const r = moveWithCollision([0, 0, 0], [10, 0, 0], 2, [floor, wall]);
    expect(r.pos[0]).toBeLessThan(1.0);
  });

  it('just integrates velocity when there are no boxes', () => {
    const r = moveWithCollision([0, 0, 0], [1, 2, 3], 0.01, []);
    expect(r.pos).toEqual([0.01, 0.02, 0.03]);
  });
});

describe('stepping up', () => {
  const STEP_FLOOR = { position: [3, -0.45, 0], size: [4, 1, 4] }; // top at y=0.05 (5 cm lip), starts at x=1
  it('walks up onto a 5 cm lip instead of stopping', () => {
    let s = { pos: [0, 0, 0], vel: [0, 0, 0] };
    for (let i = 0; i < 60; i++) s = moveWithCollision(s.pos, [2, 0, 0], 0.016, [floor, STEP_FLOOR]);
    expect(s.pos[0]).toBeGreaterThan(1.5);
    expect(s.pos[1]).toBeCloseTo(0.05);
  });
  it('still treats a 1 m high box as a wall', () => {
    const block = { position: [3, 0.5, 0], size: [4, 1, 4] }; // top at 1 m, starts at x=1
    let pos = [0, 0, 0];
    for (let i = 0; i < 60; i++) pos = moveWithCollision(pos, [2, 0, 0], 0.016, [floor, block]).pos;
    expect(pos[0]).toBeCloseTo(1 - R, 3);
    expect(pos[1]).toBeCloseTo(0);
  });
  it('does not step up into a gap too low for the player', () => {
    const lip = { position: [3, -0.45, 0], size: [4, 1, 4] };   // 5 cm lip from x=1
    const ceiling = { position: [3, 1.97, 0], size: [4, 0.5, 4] }; // underside at 1.72 → only 1.67 m clearance above the lip
    const r = moveWithCollision([0.69, 0, 0], [2, 0, 0], 0.016, [floor, ceiling, lip]);
    expect(r.pos[1]).toBe(0);
    expect(r.pos[0]).toBeCloseTo(1 - R, 3);
  });
});
