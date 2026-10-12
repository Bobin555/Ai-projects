import * as pc from 'playcanvas';
import { toast } from './ui.js';

export function enableDebug(app, colliders, player) {
  const mat = new pc.StandardMaterial();
  mat.diffuse = new pc.Color(0, 0, 0);
  mat.emissive = new pc.Color(1, 0.1, 0.1);
  mat.opacity = 0.3;
  mat.blendType = pc.BLEND_NORMAL;
  mat.depthWrite = false;
  mat.update();

  const picked = mat.clone();
  picked.emissive = new pc.Color(1, 0.85, 0);
  picked.opacity = 0.5;
  picked.update();

  const boxes = new Map(); // collider -> entity
  function show(c) {
    const box = new pc.Entity('debug-collider');
    box.addComponent('render', { type: 'box', material: mat, castShadows: false });
    box.setPosition(...c.position);
    box.setLocalScale(...c.size);
    app.root.addChild(box);
    boxes.set(c, box);
  }
  colliders.forEach(show);

  app.keyboard.on(pc.EVENT_KEYDOWN, async (e) => {
    if (e.key === pc.KEY_F) { toast(player.toggleFly() ? 'Fly mode on: Space up, C down' : 'Fly mode off'); return; }
    if (e.key !== pc.KEY_P) return;
    const text = JSON.stringify(player.getPosition().map((n) => Math.round(n * 100) / 100));
    try { await navigator.clipboard.writeText(text); toast(`Copied ${text}`); }
    catch { toast(`Position ${text} (copy blocked by browser)`); }
  });

  // Setup mode uses these to highlight, hide and bring back boxes.
  let lit = null;
  return {
    highlight(c) {
      if (lit === c) return;
      if (lit) boxes.get(lit)?.render.meshInstances.forEach((m) => { m.material = mat; });
      lit = c;
      if (c) boxes.get(c)?.render.meshInstances.forEach((m) => { m.material = picked; });
    },
    hide(c) { if (lit === c) lit = null; boxes.get(c)?.destroy(); boxes.delete(c); },
    show,
  };
}
