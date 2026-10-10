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

  for (const c of colliders) {
    const box = new pc.Entity('debug-collider');
    box.addComponent('render', { type: 'box', material: mat, castShadows: false });
    box.setPosition(...c.position);
    box.setLocalScale(...c.size);
    app.root.addChild(box);
  }

  app.keyboard.on(pc.EVENT_KEYDOWN, async (e) => {
    if (e.key !== pc.KEY_P) return;
    const text = JSON.stringify(player.getPosition().map((n) => Math.round(n * 100) / 100));
    try { await navigator.clipboard.writeText(text); toast(`Copied ${text}`); }
    catch { toast(`Position ${text} (copy blocked by browser)`); }
  });
}
