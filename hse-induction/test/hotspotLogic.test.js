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

import { nearestChange } from '../src/hotspotLogic.js';

describe('nearestChange', () => {
  it('reports the nearest ring overall, not just the one entered last', () => {
    expect(nearestChange('b', [a, b])).toEqual({ changed: true, nearest: a });
  });
  it('reports no change while the nearest ring stays the same', () => {
    expect(nearestChange('a', [a, b])).toEqual({ changed: false, nearest: a });
  });
  it('falls back to the remaining ring after leaving the nearer one', () => {
    expect(nearestChange('a', [b])).toEqual({ changed: true, nearest: b });
  });
  it('reports null after leaving every ring', () => {
    expect(nearestChange('a', [])).toEqual({ changed: true, nearest: null });
  });
});
