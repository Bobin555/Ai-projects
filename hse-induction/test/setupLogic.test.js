import { describe, it, expect } from 'vitest';
import { queueRows, stepRadius, pickNext, MIN_RADIUS, MAX_RADIUS } from '../src/setupLogic.js';

const items = ['a', 'b', 'c', 'd'].map((id) => ({ id, title: id.toUpperCase() }));

describe('queueRows', () => {
  it('marks placed, next and still to do, in file order', () => {
    expect(queueRows(items, [{ id: 'a' }], 'c')).toEqual([
      { title: 'A', state: 'placed' },
      { title: 'B', state: 'todo' },
      { title: 'C', state: 'next' },
      { title: 'D', state: 'todo' },
    ]);
  });
  it('has no next row when everything is placed', () => {
    expect(queueRows(items, items, undefined).every((r) => r.state === 'placed')).toBe(true);
  });
});

describe('pickNext', () => {
  const placed = [{ id: 'b' }];
  it('starts at the first unplaced hotspot', () => {
    expect(pickNext(items, placed, null)).toBe('a');
  });
  it('keeps the current one while it is unplaced', () => {
    expect(pickNext(items, placed, 'c')).toBe('c');
  });
  it('moves on to the next unplaced one once the current one is placed', () => {
    expect(pickNext(items, [{ id: 'b' }, { id: 'c' }], 'c')).toBe('d');
  });
  it('steps forward and back over placed ones, wrapping at both ends', () => {
    expect(pickNext(items, placed, 'a', 1)).toBe('c');
    expect(pickNext(items, placed, 'c', -1)).toBe('a');
    expect(pickNext(items, placed, 'a', -1)).toBe('d');
    expect(pickNext(items, placed, 'd', 1)).toBe('a');
  });
  it('is undefined when everything is placed', () => {
    expect(pickNext(items, items, 'a', 1)).toBeUndefined();
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
