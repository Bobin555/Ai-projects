const MAX_DT = 0.05;
const EPS = 1e-6;
const STEP_UP = 0.3; // lips, kerbs and uneven floor boxes up to 30 cm are walked over

// The player is an upright box: half-width `radius` on x/z, feet at pos[1], top at pos[1] + height.
function overlaps(pos, box, radius, height) {
  const [bx, by, bz] = box.position;
  const [hx, hy, hz] = box.size.map((s) => s / 2);
  return pos[0] + radius > bx - hx + EPS && pos[0] - radius < bx + hx - EPS
    && pos[1] + height > by - hy + EPS && pos[1] < by + hy - EPS
    && pos[2] + radius > bz - hz + EPS && pos[2] - radius < bz + hz - EPS;
}

export function moveWithCollision(pos, vel, dt, boxes, radius = 0.3, height = 1.7) {
  const step = Math.min(dt, MAX_DT);
  const p = [...pos];
  const v = [...vel];
  let grounded = false;

  // Resolve one axis at a time so the player slides along walls.
  for (const axis of [0, 1, 2]) {
    const d = v[axis] * step;
    if (d === 0) continue;
    p[axis] += d;
    for (const box of boxes) {
      if (!overlaps(p, box, radius, height)) continue;
      const centre = box.position[axis];
      const half = box.size[axis] / 2;
      if (axis === 1) {
        if (d < 0) { p[1] = centre + half; grounded = true; } else p[1] = centre - half - height;
      } else {
        const top = box.position[1] + box.size[1] / 2;
        const stepped = [p[0], top, p[2]];
        if (top - p[1] <= STEP_UP && !boxes.some((b) => overlaps(stepped, b, radius, height))) {
          p[1] = top;
          continue;
        }
        p[axis] = d > 0 ? centre - half - radius : centre + half + radius;
      }
      v[axis] = 0;
    }
  }

  // Standing still on a surface still counts as grounded.
  if (!grounded && v[1] === 0) {
    grounded = boxes.some((b) => overlaps([p[0], p[1] - 0.01, p[2]], b, radius, height));
  }
  return { pos: p, vel: v, grounded };
}
