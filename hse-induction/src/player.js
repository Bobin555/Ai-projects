import * as pc from 'playcanvas';
import { moveWithCollision, MAX_DT } from './collision.js';

const WALK = 1.4;
const RUN = 3;
const GRAVITY = -9.8;
const EYE = 1.6;
const LOOK_SPEED = 0.15; // degrees per pixel
const TURN_SPEED = 90; // degrees per second with the arrow keys
const FLY_SPEED = 3;
const FALL_LIMIT = 20;
const MAX_FRAME = 0.25; // a longer frame (tab switch, hitch) is cut short rather than replayed

export function createPlayer(app, camera, site, colliders) {
  const start = site.start;
  let pos = [...start.position];
  let vel = [0, 0, 0];
  let yaw = start.yaw ?? 0;
  let pitch = 0;
  let paused = false;
  let flying = false;
  const kb = app.keyboard;
  const canvas = app.graphicsDevice.canvas;

  canvas.addEventListener('click', () => {
    if (document.pointerLockElement !== canvas) canvas.requestPointerLock?.()?.catch?.(() => {}); // Chrome refuses a re-lock right after Esc
  });
  // Look with the locked mouse, or by dragging with a button held (fallback if the lock is refused).
  app.mouse.on(pc.EVENT_MOUSEMOVE, (e) => {
    const dragging = e.buttons?.some(Boolean);
    if (document.pointerLockElement !== canvas && !dragging) return;
    yaw -= e.dx * LOOK_SPEED;
    pitch = Math.max(-85, Math.min(85, pitch - e.dy * LOOK_SPEED));
  });

  function resetToStart() {
    pos = [...start.position];
    vel = [0, 0, 0];
  }

  function update(dt) {
    const turn = (kb.isPressed(pc.KEY_LEFT) ? 1 : 0) - (kb.isPressed(pc.KEY_RIGHT) ? 1 : 0);
    const tilt = (kb.isPressed(pc.KEY_UP) ? 1 : 0) - (kb.isPressed(pc.KEY_DOWN) ? 1 : 0);
    yaw += turn * TURN_SPEED * dt;
    pitch = Math.max(-85, Math.min(85, pitch + tilt * TURN_SPEED * dt));

    const speed = kb.isPressed(pc.KEY_SHIFT) ? RUN : WALK;
    const fwd = (kb.isPressed(pc.KEY_W) ? 1 : 0) - (kb.isPressed(pc.KEY_S) ? 1 : 0);
    const side = (kb.isPressed(pc.KEY_D) ? 1 : 0) - (kb.isPressed(pc.KEY_A) ? 1 : 0);
    // PlayCanvas cameras look down -Z; yaw rotates around +Y.
    const r = (yaw * Math.PI) / 180;
    let mx = -Math.sin(r) * fwd + Math.cos(r) * side;
    let mz = -Math.cos(r) * fwd - Math.sin(r) * side;
    const len = Math.hypot(mx, mz);
    if (len > 0 && !paused) { mx = (mx / len) * speed; mz = (mz / len) * speed; } else { mx = 0; mz = 0; }

    // Move in steps of at most MAX_DT so slow frame rates keep full speed without tunnelling through walls.
    for (let left = Math.min(dt, MAX_FRAME); left > 1e-6; left -= MAX_DT) {
      const step = Math.min(left, MAX_DT);
      if (flying) {
        // Debug fly mode: no gravity, no walls; Space up, C down.
        const up = (kb.isPressed(pc.KEY_SPACE) ? 1 : 0) - (kb.isPressed(pc.KEY_C) ? 1 : 0);
        const k = (FLY_SPEED / WALK) * step;
        pos = [pos[0] + mx * k, pos[1] + up * FLY_SPEED * step, pos[2] + mz * k];
        vel = [0, 0, 0];
      } else {
        vel = [mx, vel[1] + GRAVITY * step, mz];
        const res = moveWithCollision(pos, vel, step, colliders);
        pos = res.pos;
        vel = res.vel;
        if (pos[1] < start.position[1] - FALL_LIMIT) resetToStart();
      }
    }

    camera.setPosition(pos[0], pos[1] + EYE, pos[2]);
    camera.setEulerAngles(pitch, yaw, 0);
  }

  app.on('update', update);
  return { update, getPosition: () => [...pos], setYaw: (y) => { yaw = y; }, resetToStart, setPaused: (p) => { paused = p; }, toggleFly: () => (flying = !flying) };
}
