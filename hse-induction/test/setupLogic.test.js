import { describe, it, expect } from 'vitest';
import { queueRows, stepRadius, pickNext, pickBox, MIN_RADIUS, MAX_RADIUS } from '../src/setupLogic.js';

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

describe('pickBox', () => {
  const floor = { position: [0, -0.1, 0], size: [20, 0.2, 20] };
  const near = { position: [0, 1.25, -2], size: [1, 2.5, 1] };
  const far = { position: [0, 1.25, -5], size: [1, 2.5, 1] };
  const boxes = [floor, far, near];
  it('picks the nearest wall box straight ahead', () => {
    expect(pickBox([0, 1.6, 0], [0, 0, -1], boxes)).toBe(2);
  });
  it('ignores floor boxes', () => {
    expect(pickBox([0, 1.6, 0], [0, -1, 0], boxes)).toBe(-1);
  });
  it('picks the box you are standing inside', () => {
    expect(pickBox([0, 1.6, -2], [1, 0, 0], boxes)).toBe(2);
  });
  it('misses when nothing is ahead or it is too far', () => {
    expect(pickBox([0, 1.6, 0], [0, 0, 1], boxes)).toBe(-1);
    expect(pickBox([0, 1.6, 0], [0, 0, -1], [far], 3)).toBe(-1);
  });
});
