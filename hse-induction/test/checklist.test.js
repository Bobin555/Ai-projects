import { describe, it, expect } from 'vitest';
import { createChecklist } from '../src/checklist.js';

describe('createChecklist', () => {
  it('starts at 0 of N', () => {
    const c = createChecklist(['a', 'b', 'c']);
    expect(c.found()).toBe(0);
    expect(c.total()).toBe(3);
    expect(c.isComplete()).toBe(false);
  });
  it('counts a hotspot only the first time', () => {
    const c = createChecklist(['a', 'b']);
    expect(c.markFound('a')).toBe(true);
    expect(c.markFound('a')).toBe(false);
    expect(c.found()).toBe(1);
    expect(c.isFound('a')).toBe(true);
    expect(c.isFound('b')).toBe(false);
  });
  it('ignores unknown ids', () => {
    const c = createChecklist(['a']);
    expect(c.markFound('zzz')).toBe(false);
    expect(c.found()).toBe(0);
  });
  it('is complete once every id is found', () => {
    const c = createChecklist(['a', 'b']);
    c.markFound('a');
    c.markFound('b');
    expect(c.isComplete()).toBe(true);
  });
});
