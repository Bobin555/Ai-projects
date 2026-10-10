import { validateSite } from '../src/siteData.js';

// Check a site.json body before the dev server writes it. Never write anything that wouldn't load.
export function checkSave(body) {
  let data;
  try {
    data = JSON.parse(body);
  } catch (err) {
    return { ok: false, error: `Not valid JSON: ${err.message}` };
  }
  const errors = validateSite(data);
  if (errors.length) return { ok: false, error: errors.join('\n') };
  return { ok: true, json: `${JSON.stringify(data, null, 2)}\n` };
}
