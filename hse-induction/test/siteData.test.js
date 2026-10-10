import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { validateSite } from '../src/siteData.js';

const sample = () => JSON.parse(readFileSync(new URL('../public/site.json', import.meta.url), 'utf8'));
const errorsFor = (mutate) => { const d = sample(); mutate(d); return validateSite(d).join('\n'); };

describe('validateSite', () => {
  it('accepts the sample site.json', () => {
    expect(validateSite(sample())).toEqual([]);
  });
  it('requires splatUrl', () => {
    expect(errorsFor(d => { delete d.splatUrl; })).toContain('splatUrl');
  });
  it('requires start.position to be 3 numbers', () => {
    expect(errorsFor(d => { d.start.position = [0, 1]; })).toContain('start.position');
  });
  it('rejects zero or negative collider sizes', () => {
    expect(errorsFor(d => { d.colliders[0].size = [1, 0, -2]; })).toContain('colliders[0].size');
  });
  it('requires 2-3 points per hotspot', () => {
    expect(errorsFor(d => { d.hotspots[0].points = ['one']; })).toContain('hotspots[0].points');
    expect(errorsFor(d => { d.hotspots[0].points = ['a', 'b', 'c', 'd']; })).toContain('hotspots[0].points');
  });
  it('requires a positive radius', () => {
    expect(errorsFor(d => { d.hotspots[1].radius = 0; })).toContain('hotspots[1].radius');
  });
  it('rejects duplicate hotspot ids', () => {
    expect(errorsFor(d => { d.hotspots[1].id = d.hotspots[0].id; })).toContain('duplicate id');
  });
  it('requires a non-empty title', () => {
    expect(errorsFor(d => { d.hotspots[0].title = ' '; })).toContain('hotspots[0].title');
  });
  it('reports every error, not just the first', () => {
    expect(validateSite({}).length).toBeGreaterThan(1);
  });
});

describe('start position', () => {
  it('rejects a start position inside a collider', () => {
    expect(errorsFor(d => { d.colliders.push({ position: [0, 1, 0], size: [2, 2, 2] }); })).toContain('start.position: inside colliders[1]');
  });
  it('accepts feet resting exactly on a floor top', () => {
    expect(validateSite(sample())).toEqual([]);
  });
});

describe('loadSite', () => {
  it('reports broken JSON as invalid site data', async () => {
    const { loadSite } = await import('../src/siteData.js');
    const realFetch = globalThis.fetch;
    globalThis.fetch = async () => new Response('{ "splatUrl": ', { status: 200 });
    try {
      await expect(loadSite()).rejects.toMatchObject({ invalidSite: true });
    } finally {
      globalThis.fetch = realFetch;
    }
  });
});

describe('splatRotation', () => {
  it('is optional', () => {
    expect(validateSite(sample())).toEqual([]);
  });
  it('accepts 3 numbers in degrees', () => {
    expect(errorsFor(d => { d.splatRotation = [-90, 0, 0]; })).toBe('');
  });
  it('rejects anything else', () => {
    expect(errorsFor(d => { d.splatRotation = [-90, 0]; })).toContain('splatRotation');
  });
});

describe('splatPosition and empty hotspots', () => {
  it('splatPosition is optional and takes 3 numbers', () => {
    expect(errorsFor(d => { d.splatPosition = [1, 2, 3]; })).toBe('');
    expect(errorsFor(d => { d.splatPosition = [1, 2]; })).toContain('splatPosition');
  });
  it('allows a site with no hotspots yet', () => {
    expect(errorsFor(d => { d.hotspots = []; })).toBe('');
  });
});
