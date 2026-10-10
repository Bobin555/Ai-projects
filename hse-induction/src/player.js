import * as pc from 'playcanvas';
import { moveWithCollision } from './collision.js';

const WALK = 1.4;
const RUN = 3;
const GRAVITY = -9.8;
const EYE = 1.6;
const LOOK_SPEED = 0.15; // degrees per pixel
const FALL_LIMIT = 20;

export function createPlayer(app, camera, site, colliders) {
  const start = site.start;
  let pos = [...start.position];
  let vel = [0, 0, 0];
  let yaw = start.yaw ?? 0;
  let pitch = 0;
  const kb = app.keyboard;
  const canvas = app.graphicsDevice.canvas;

  canvas.addEventListener('click', () => {
    if (document.pointerLockElement !== canvas) canvas.requestPointerLock?.();
  });
  app.mouse.on(pc.EVENT_MOUSEMOVE, (e) => {
    if (document.pointerLockElement !== canvas) return;
    yaw -= e.dx * LOOK_SPEED;
    pitch = Math.max(-85, Math.min(85, pitch - e.dy * LOOK_SPEED));
  });

  function resetToStart() {
    pos = [...start.position];
    vel = [0, 0, 0];
  }

  function update(dt) {
    const speed = kb.isPressed(pc.KEY_SHIFT) ? RUN : WALK;
    const fwd = (kb.isPressed(pc.KEY_W) ? 1 : 0) - (kb.isPressed(pc.KEY_S) ? 1 : 0);
    const side = (kb.isPressed(pc.KEY_D) ? 1 : 0) - (kb.isPressed(pc.KEY_A) ? 1 : 0);
    // PlayCanvas cameras look down -Z; yaw rotates around +Y.
    const r = (yaw * Math.PI) / 180;
    let mx = -Math.sin(r) * fwd + Math.cos(r) * side;
    let mz = -Math.cos(r) * fwd - Math.sin(r) * side;
    const len = Math.hypot(mx, mz);
    if (len > 0) { mx = (mx / len) * speed; mz = (mz / len) * speed; }

    vel = [mx, vel[1] + GRAVITY * Math.min(dt, 0.05), mz];
    const res = moveWithCollision(pos, vel, dt, colliders);
    pos = res.pos;
    vel = res.vel;
    if (pos[1] < start.position[1] - FALL_LIMIT) resetToStart();

    camera.setPosition(pos[0], pos[1] + EYE, pos[2]);
    camera.setEulerAngles(pitch, yaw, 0);
  }

  app.on('update', update);
  return { update, getPosition: () => [...pos], resetToStart };
}
