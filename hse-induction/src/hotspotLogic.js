const flatDistance = (p, h) => Math.hypot(p[0] - h.position[0], p[2] - h.position[2]);

// Every hotspot whose ring (x/z only) contains the player, nearest first.
export function hotspotsInside(pos, hotspots) {
  return hotspots
    .map((h) => ({ h, d: flatDistance(pos, h) }))
    .filter(({ h, d }) => d <= h.radius)
    .sort((x, y) => x.d - y.d)
    .map(({ h }) => h);
}

export function newlyEntered(prevIds, nowIds) {
  return [...nowIds].filter((id) => !prevIds.has(id));
}
