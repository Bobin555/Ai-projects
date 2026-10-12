import { validateSite } from '../src/siteData.js';

// Check a save before the dev server writes it. Never write anything that wouldn't load.
// With `current` (the file on disk), only `hotspots` and optionally `colliders` are taken from the request, and
// colliders may only lose boxes (setup's X key): a stale setup tab or another page can't move walls, add them,
// or change the levelling or splat URL.
export function checkSave(body, current = null) {
  let data;
  try {
    data = JSON.parse(body);
  } catch (err) {
    return { ok: false, error: `Not valid JSON: ${err.message}` };
  }
  if (current) {
    if (!Array.isArray(data?.hotspots)) return { ok: false, error: 'Expected { hotspots: [...] }' };
    const next = { ...current, hotspots: data.hotspots };
    if (data.colliders !== undefined) {
      // Boxes deleted in setup are kept in removedColliders so Z can bring them back later.
      const key = (c) => JSON.stringify(c);
      const known = [...(current.colliders ?? []), ...(current.removedColliders ?? [])];
      const allowed = new Set(known.map(key));
      if (!Array.isArray(data.colliders) || data.colliders.some((c) => !allowed.has(key(c)))) {
        return { ok: false, error: 'Walls changed on disk (new-site was rerun?). Reload the page, then try again.' };
      }
      const kept = new Set(data.colliders.map(key));
      const isFloor = (c) => c.position[1] + c.size[1] / 2 <= 0.01;
      if (known.some((c) => isFloor(c) && !kept.has(key(c)))) {
        return { ok: false, error: 'Floor boxes can only be removed by rerunning new-site.' };
      }
      next.colliders = data.colliders;
      next.removedColliders = known.filter((c) => !kept.has(key(c)));
      if (!next.removedColliders.length) delete next.removedColliders;
    }
    data = next;
  }
  const errors = validateSite(data);
  if (errors.length) return { ok: false, error: errors.join('\n') };
  return { ok: true, json: `${JSON.stringify(data, null, 2)}\n` };
}
