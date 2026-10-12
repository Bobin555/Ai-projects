import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { checkSave } from '../scripts/saveSite.js';

const sample = readFileSync(new URL('./fixtures/site.json', import.meta.url), 'utf8');

describe('checkSave', () => {
  it('accepts a valid site and pretty-prints it', () => {
    const r = checkSave(JSON.stringify(JSON.parse(sample)));
    expect(r.ok).toBe(true);
    expect(r.json).toBe(`${JSON.stringify(JSON.parse(sample), null, 2)}\n`);
  });
  it('refuses something that is not JSON', () => {
    const r = checkSave('{ nope');
    expect(r.ok).toBe(false);
    expect(r.error).toMatch(/JSON/);
  });
  it('refuses an invalid site with the validation message', () => {
    const d = JSON.parse(sample);
    d.hotspots[0].points = ['only one'];
    const r = checkSave(JSON.stringify(d));
    expect(r.ok).toBe(false);
    expect(r.error).toContain('hotspots[0].points');
  });
});

describe('checkSave with the file on disk', () => {
  const onDisk = JSON.parse(sample);
  it('only takes hotspots from the request; everything else comes from the file', () => {
    const body = JSON.stringify({ hotspots: [], splatUrl: 'evil.sog', splatPosition: [9, 9, 9] });
    const r = checkSave(body, onDisk);
    expect(r.ok).toBe(true);
    const saved = JSON.parse(r.json);
    expect(saved.splatUrl).toBe(onDisk.splatUrl);
    expect(saved.colliders).toEqual(onDisk.colliders);
    expect(saved.hotspots).toEqual([]);
  });
  it('refuses a body without a hotspots list', () => {
    expect(checkSave(JSON.stringify({ splatUrl: 'x' }), onDisk).ok).toBe(false);
  });
});

describe('checkSave: removing walls in setup', () => {
  const onDisk = JSON.parse(sample);
  onDisk.colliders = [{ position: [3, 1.25, 3], size: [1, 2.5, 1] }, ...onDisk.colliders];
  it('accepts a colliders list that only drops boxes from the file', () => {
    const r = checkSave(JSON.stringify({ hotspots: onDisk.hotspots, colliders: onDisk.colliders.slice(1) }), onDisk);
    expect(r.ok).toBe(true);
    expect(JSON.parse(r.json).colliders).toEqual(onDisk.colliders.slice(1));
  });
  it('remembers removed boxes so they can be put back', () => {
    const r1 = JSON.parse(checkSave(JSON.stringify({ hotspots: [], colliders: onDisk.colliders.slice(1) }), onDisk).json);
    expect(r1.removedColliders).toEqual([onDisk.colliders[0]]);
    const r2 = JSON.parse(checkSave(JSON.stringify({ hotspots: [], colliders: onDisk.colliders }), r1).json);
    expect(r2.colliders).toEqual(onDisk.colliders);
    expect(r2.removedColliders).toBeUndefined();
  });
  it('refuses removing a floor box', () => {
    expect(checkSave(JSON.stringify({ hotspots: [], colliders: [] }), onDisk).ok).toBe(false);
  });
  it('refuses a box that is not in the file (stale tab or a new box)', () => {
    const extra = { position: [9, 1, 9], size: [1, 2, 1] };
    const r = checkSave(JSON.stringify({ hotspots: [], colliders: [...onDisk.colliders, extra] }), onDisk);
    expect(r.ok).toBe(false);
    expect(r.error).toMatch(/reload/i);
  });
});
