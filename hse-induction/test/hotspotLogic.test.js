import { describe, it, expect } from 'vitest';
import { hotspotsInside, newlyEntered } from '../src/hotspotLogic.js';

const a = { id: 'a', position: [0, 0, 0], radius: 1.5 };
const b = { id: 'b', position: [2, 0, 0], radius: 1.5 };

describe('hotspotsInside', () => {
  it('counts a player exactly on the radius as inside', () => {
    expect(hotspotsInside([1.5, 0, 0], [a]).map((h) => h.id)).toEqual(['a']);
  });
  it('counts a player just past the radius as outside', () => {
    expect(hotspotsInside([1.51, 0, 0], [a])).toEqual([]);
  });
  it('ignores height difference', () => {
    expect(hotspotsInside([0, 10, 0], [a]).map((h) => h.id)).toEqual(['a']);
  });
  it('returns overlapping hotspots nearest first', () => {
    expect(hotspotsInside([1.2, 0, 0], [a, b]).map((h) => h.id)).toEqual(['b', 'a']);
  });
});

describe('newlyEntered', () => {
  it('returns nothing when standing still inside', () => {
    expect(newlyEntered(new Set(['a']), new Set(['a']))).toEqual([]);
  });
  it('returns the id again after leaving and re-entering', () => {
    expect(newlyEntered(new Set(['a']), new Set())).toEqual([]);
    expect(newlyEntered(new Set(), new Set(['a']))).toEqual(['a']);
  });
});
