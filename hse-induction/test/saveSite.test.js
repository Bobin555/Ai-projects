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
