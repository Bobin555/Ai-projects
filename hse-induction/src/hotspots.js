import * as pc from 'playcanvas';
import { hotspotsInside, newlyEntered, nearestChange } from './hotspotLogic.js';

// onEnter(hotspots[]) gets the rings just entered this frame; onNearestChange(hotspot|null) fires when the nearest ring the player stands in changes.
// Returns { add(hotspot), remove(id) } so setup mode can change rings while the app runs.
export function createHotspots(app, initial, getPlayerPos, { onEnter, onNearestChange }) {
  const hotspots = [];
  const rings = new Map();
  const mat = new pc.StandardMaterial();
  mat.diffuse = new pc.Color(0, 0, 0);
  mat.emissive = new pc.Color(1, 0.7, 0);
  mat.update();

  function add(h) {
    const mesh = pc.Mesh.fromGeometry(app.graphicsDevice, new pc.TorusGeometry({ ringRadius: h.radius, tubeRadius: 0.04, segments: 64 }));
    const ring = new pc.Entity(`hotspot-${h.id}`);
    ring.addComponent('render', { meshInstances: [new pc.MeshInstance(mesh, mat)], castShadows: false });
    ring.setPosition(h.position[0], h.position[1] + 0.1, h.position[2]);
    app.root.addChild(ring);
    rings.set(h.id, ring);
    hotspots.push(h);
  }

  function remove(id) {
    rings.get(id)?.destroy();
    rings.delete(id);
    const i = hotspots.findIndex((h) => h.id === id);
    if (i >= 0) hotspots.splice(i, 1);
  }

  initial.forEach(add);

  let prev = new Set();
  let prevNearest = null;
  let t = 0;
  app.on('update', (dt) => {
    t += dt;
    mat.emissiveIntensity = 0.6 + 0.4 * Math.sin(t * 3);
    mat.update();

    const inside = hotspotsInside(getPlayerPos(), hotspots);
    const now = new Set(inside.map((h) => h.id));
    const entered = new Set(newlyEntered(prev, now));
    const justEntered = inside.filter((h) => entered.has(h.id));
    if (justEntered.length) onEnter(justEntered);
    const { changed, nearest } = nearestChange(prevNearest, inside);
    if (changed) onNearestChange(nearest);
    prevNearest = nearest?.id ?? null;
    prev = now;
  });
  return { add, remove };
}
