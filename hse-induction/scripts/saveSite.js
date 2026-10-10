import { validateSite } from '../src/siteData.js';

// Check a save before the dev server writes it. Never write anything that wouldn't load.
// With `current` (the file on disk), only `hotspots` is taken from the request: a stale setup tab or another
// page can't overwrite the levelling, walls or splat URL.
export function checkSave(body, current = null) {
  let data;
  try {
    data = JSON.parse(body);
  } catch (err) {
    return { ok: false, error: `Not valid JSON: ${err.message}` };
  }
  if (current) {
    if (!Array.isArray(data?.hotspots)) return { ok: false, error: 'Expected { hotspots: [...] }' };
    data = { ...current, hotspots: data.hotspots };
  }
  const errors = validateSite(data);
  if (errors.length) return { ok: false, error: errors.join('\n') };
  return { ok: true, json: `${JSON.stringify(data, null, 2)}\n` };
}
