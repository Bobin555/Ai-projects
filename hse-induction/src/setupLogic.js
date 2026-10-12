// Pure helpers for setup mode (kept out of setup.js so they can be tested without a browser).

export const MIN_RADIUS = 0.5;
export const MAX_RADIUS = 4;
const STEP = 0.25;

// One row per hotspot in hotspots.md order: 'placed', 'next' (the one H places), 'skipped' or 'todo'.
export function queueRows(items, placed, skipped, nextId) {
  const done = new Set(placed.map((p) => p.id));
  return items.map((it) => ({
    title: it.title,
    state: done.has(it.id) ? 'placed' : it.id === nextId ? 'next' : skipped.has(it.id) ? 'skipped' : 'todo',
  }));
}

// Ring size one step up (dir 1) or down (dir -1), on the 0.25 m grid and within the limits.
export function stepRadius(radius, dir) {
  const snapped = dir > 0 ? Math.floor(radius / STEP + 1e-9) : Math.ceil(radius / STEP - 1e-9);
  return Math.min(MAX_RADIUS, Math.max(MIN_RADIUS, (snapped + dir) * STEP));
}
