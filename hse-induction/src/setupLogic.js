// Pure helpers for setup mode (kept out of setup.js so they can be tested without a browser).

export const MIN_RADIUS = 0.5;
export const MAX_RADIUS = 4;
const STEP = 0.25;

// One row per hotspot in hotspots.md order: 'placed', 'next' (the one H places) or 'todo'.
export function queueRows(items, placed, nextId) {
  const done = new Set(placed.map((p) => p.id));
  return items.map((it) => ({ title: it.title, state: done.has(it.id) ? 'placed' : it.id === nextId ? 'next' : 'todo' }));
}

// Id of the hotspot H will place. dir 0 keeps the current one while it is unplaced, otherwise moves on;
// dir 1 / -1 steps to the next / previous unplaced one, wrapping round. Undefined when all are placed.
export function pickNext(items, placed, currentId, dir = 0) {
  const done = new Set(placed.map((p) => p.id));
  const at = items.findIndex((it) => it.id === currentId);
  if (dir === 0 && at >= 0 && !done.has(currentId)) return currentId;
  const step = dir < 0 ? -1 : 1;
  const n = items.length;
  for (let k = 1; k <= n; k++) {
    const it = items[(((at + step * k) % n) + n) % n];
    if (!done.has(it.id)) return it.id;
  }
  return undefined;
}

// Ring size one step up (dir 1) or down (dir -1), on the 0.25 m grid and within the limits.
export function stepRadius(radius, dir) {
  const snapped = dir > 0 ? Math.floor(radius / STEP + 1e-9) : Math.ceil(radius / STEP - 1e-9);
  return Math.min(MAX_RADIUS, Math.max(MIN_RADIUS, (snapped + dir) * STEP));
}
