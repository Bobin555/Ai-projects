import { describe, it, expect } from 'vitest';
import { queueRows, stepRadius, MIN_RADIUS, MAX_RADIUS } from '../src/setupLogic.js';

const items = ['a', 'b', 'c', 'd'].map((id) => ({ id, title: id.toUpperCase() }));

describe('queueRows', () => {
  it('marks placed, next, skipped and still to do, in file order', () => {
    const rows = queueRows(items, [{ id: 'a' }], new Set(['b']), 'c');
    expect(rows).toEqual([
      { title: 'A', state: 'placed' },
      { title: 'B', state: 'skipped' },
      { title: 'C', state: 'next' },
      { title: 'D', state: 'todo' },
    ]);
  });
  it('has no next row when everything is placed', () => {
    expect(queueRows(items, items, new Set(), undefined).every((r) => r.state === 'placed')).toBe(true);
  });
});

describe('stepRadius', () => {
  it('steps by 0.25 m', () => {
    expect(stepRadius(1.5, 1)).toBe(1.75);
    expect(stepRadius(1.5, -1)).toBe(1.25);
  });
  it('stays within the limits', () => {
    expect(stepRadius(MIN_RADIUS, -1)).toBe(MIN_RADIUS);
    expect(stepRadius(MAX_RADIUS, 1)).toBe(MAX_RADIUS);
  });
  it('snaps an odd saved size onto the grid', () => {
    expect(stepRadius(1.3, 1)).toBe(1.5);
  });
});
