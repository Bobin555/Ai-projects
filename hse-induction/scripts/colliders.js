// Turn levelled splat positions (Y-up, floor at y = 0) into box colliders and a start point.

const FLOOR_BAND = 0.15;          // |y| within this counts as floor
const SOLID_BAND = [0.3, 1.8];    // body height: anything here blocks walking
const WALL_HEIGHT = 2.5;
const FLOOR_THICKNESS = 0.2;
const CLEARANCE = 0.6;            // start point keeps this far from walls and floor edges

const key = (i, k) => `${i},${k}`;
const unkey = (s) => s.split(',').map(Number);

// Merge a set of grid cells into rectangles: runs along x per row, stacked across rows when identical.
function mergeCells(cells) {
  const rows = new Map();
  for (const c of cells) {
    const [i, k] = unkey(c);
    if (!rows.has(k)) rows.set(k, []);
    rows.get(k).push(i);
  }
  const rects = [];
  let open = new Map(); // "i0,i1" -> rect being grown downwards in k
  for (const k of [...rows.keys()].sort((a, b) => a - b)) {
    const xs = rows.get(k).sort((a, b) => a - b);
    const runs = [];
    for (const i of xs) {
      const last = runs[runs.length - 1];
      if (last && i === last[1] + 1) last[1] = i; else runs.push([i, i]);
    }
    const next = new Map();
    for (const [i0, i1] of runs) {
      const id = key(i0, i1);
      const r = open.get(id);
      if (r && r.k1 === k - 1) { r.k1 = k; next.set(id, r); open.delete(id); } else next.set(id, { i0, i1, k0: k, k1: k });
    }
    rects.push(...open.values());
    open = next;
  }
  rects.push(...open.values());
  return rects;
}

function rectToBox({ i0, i1, k0, k1 }, cell, y0, y1) {
  const [xa, xb, za, zb] = [i0 * cell, (i1 + 1) * cell, k0 * cell, (k1 + 1) * cell];
  return { position: [(xa + xb) / 2, (y0 + y1) / 2, (za + zb) / 2], size: [xb - xa, y1 - y0, zb - za] };
}

function build(positions, cell, minSolid) {
  const floorCells = new Set();
  const solidCount = new Map();
  for (let n = 0; n < positions.length; n += 3) {
    const [x, y, z] = [positions[n], positions[n + 1], positions[n + 2]];
    const c = key(Math.floor(x / cell), Math.floor(z / cell));
    if (Math.abs(y) <= FLOOR_BAND) floorCells.add(c);
    if (y >= SOLID_BAND[0] && y <= SOLID_BAND[1]) solidCount.set(c, (solidCount.get(c) ?? 0) + 1);
  }
  const solidCells = new Set([...solidCount].filter(([, n]) => n >= minSolid).map(([c]) => c));
  const colliders = [
    ...mergeCells(floorCells).map((r) => rectToBox(r, cell, -FLOOR_THICKNESS, 0)),
    ...mergeCells(solidCells).map((r) => rectToBox(r, cell, 0, WALL_HEIGHT)),
  ];
  return { colliders, floorCells, solidCells, cell };
}

export function buildColliders(positions, { cell = 0.25, minSolid = 8, maxBoxes = 400 } = {}) {
  let result = build(positions, cell, minSolid);
  // Coarser grid until the box count fits; minSolid scales with cell area so density stays comparable.
  while (result.colliders.length > maxBoxes && result.cell < 5) {
    const next = result.cell * 1.5;
    result = build(positions, next, Math.round(minSolid * (next / cell) ** 2));
  }
  return result;
}

// Open floor cell nearest the floor's middle, at least CLEARANCE from walls and from the floor's edge.
export function pickStart({ floorCells, solidCells, cell }) {
  const free = [...floorCells].filter((c) => !solidCells.has(c));
  if (!free.length) return null;
  const freeSet = new Set(free);

  // Multi-source BFS (8-neighbour) from every blocked cell around the free area.
  const dist = new Map();
  const queue = [];
  for (const c of free) {
    const [i, k] = unkey(c);
    for (let di = -1; di <= 1; di++) for (let dk = -1; dk <= 1; dk++) {
      const nb = key(i + di, k + dk);
      if (!freeSet.has(nb) && !dist.has(nb)) { dist.set(nb, 0); queue.push(nb); }
    }
  }
  for (let q = 0; q < queue.length; q++) {
    const [i, k] = unkey(queue[q]);
    const d = dist.get(queue[q]);
    for (let di = -1; di <= 1; di++) for (let dk = -1; dk <= 1; dk++) {
      const nb = key(i + di, k + dk);
      if (freeSet.has(nb) && !dist.has(nb)) { dist.set(nb, d + 1); queue.push(nb); }
    }
  }

  // Chebyshev steps underestimate true distance, so (d - 0.5) * cell >= CLEARANCE is a safe test.
  const minSteps = Math.ceil(CLEARANCE / cell + 0.5);
  const centre = free.reduce((s, c) => { const [i, k] = unkey(c); return [s[0] + i, s[1] + k]; }, [0, 0]).map((v) => v / free.length);
  const candidates = free.filter((c) => dist.get(c) >= minSteps);
  if (!candidates.length) return null;
  const best = candidates.reduce((a, b) => {
    const da = Math.hypot(...unkey(a).map((v, j) => v - centre[j]));
    const db = Math.hypot(...unkey(b).map((v, j) => v - centre[j]));
    return db < da ? b : a;
  });
  const [bi, bk] = unkey(best);

  // Face the longest open run among 8 directions.
  let yaw = 0;
  let longest = -1;
  for (const [di, dk] of [[0, -1], [1, -1], [1, 0], [1, 1], [0, 1], [-1, 1], [-1, 0], [-1, -1]]) {
    let steps = 0;
    while (freeSet.has(key(bi + di * (steps + 1), bk + dk * (steps + 1)))) steps++;
    if (steps > longest) { longest = steps; yaw = (Math.atan2(-di, -dk) * 180) / Math.PI; }
  }
  return { position: [(bi + 0.5) * cell, 0, (bk + 0.5) * cell], yaw };
}
