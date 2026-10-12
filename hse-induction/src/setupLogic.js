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

// Index of the nearest wall box the ray (origin, unit dir) hits within maxDist, or -1. Floor boxes (top at y <= 0)
// are skipped so you can't delete the ground. Standing inside a box counts as hitting it.
export function pickBox(origin, dir, boxes, maxDist = 15) {
  let best = -1;
  let bestT = maxDist;
  boxes.forEach((b, i) => {
    if (b.position[1] + b.size[1] / 2 <= 0.01) return;
    let t0 = 0;
    let t1 = bestT;
    for (let a = 0; a < 3; a++) {
      const lo = b.position[a] - b.size[a] / 2;
      const hi = b.position[a] + b.size[a] / 2;
      if (Math.abs(dir[a]) < 1e-9) { if (origin[a] < lo || origin[a] > hi) return; continue; }
      let ta = (lo - origin[a]) / dir[a];
      let tb = (hi - origin[a]) / dir[a];
      if (ta > tb) [ta, tb] = [tb, ta];
      t0 = Math.max(t0, ta);
      t1 = Math.min(t1, tb);
      if (t0 > t1) return;
    }
    best = i;
    bestT = t0;
  });
  return best;
}
