import { describe, it, expect } from 'vitest';
import { moveWithCollision } from '../src/collision.js';

const floor = { position: [0, -0.5, 0], size: [40, 1, 40] }; // top at y=0
const R = 0.3;

describe('moveWithCollision', () => {
  it('stays on the floor when standing still', () => {
    const r = moveWithCollision([0, 0, 0], [0, 0, 0], 0.016, [floor]);
    expect(r.pos[1]).toBeCloseTo(0);
    expect(r.grounded).toBe(true);
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
    expect(s.grounded).toBe(true);
  });

  it('clamps a huge dt so the player cannot tunnel through a thin wall', () => {
    const wall = { position: [1.1, 1, 0], size: [0.2, 2, 10] }; // 1 m ahead
    const r = moveWithCollision([0, 0, 0], [10, 0, 0], 2, [floor, wall]);
    expect(r.pos[0]).toBeLessThan(1.0);
  });

  it('just integrates velocity when there are no boxes', () => {
    const r = moveWithCollision([0, 0, 0], [1, 2, 3], 0.01, []);
    expect(r.pos).toEqual([0.01, 0.02, 0.03]);
    expect(r.grounded).toBe(false);
  });
});
