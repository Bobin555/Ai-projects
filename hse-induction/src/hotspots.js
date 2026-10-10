import * as pc from 'playcanvas';
import { hotspotsInside, newlyEntered } from './hotspotLogic.js';

// onEnter(hotspots[]) gets the rings just entered this frame, nearest first; onLeaveAll() fires when the player is in no ring.
export function createHotspots(app, hotspots, getPlayerPos, { onEnter, onLeaveAll }) {
  const mat = new pc.StandardMaterial();
  mat.diffuse = new pc.Color(0, 0, 0);
  mat.emissive = new pc.Color(1, 0.7, 0);
  mat.update();

  for (const h of hotspots) {
    const mesh = pc.Mesh.fromGeometry(app.graphicsDevice, new pc.TorusGeometry({ ringRadius: h.radius, tubeRadius: 0.04, segments: 64 }));
    const ring = new pc.Entity(`hotspot-${h.id}`);
    ring.addComponent('render', { meshInstances: [new pc.MeshInstance(mesh, mat)], castShadows: false });
    ring.setPosition(h.position[0], h.position[1] + 0.1, h.position[2]);
    app.root.addChild(ring);
  }

  let prev = new Set();
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
    if (now.size === 0 && prev.size > 0) onLeaveAll();
    prev = now;
  });
}
