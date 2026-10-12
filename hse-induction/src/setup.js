import * as pc from 'playcanvas';
import { parseHotspotsMd, mergeHotspots, unmatchedPlaced } from './hotspotsMd.js';
import { queueRows, stepRadius, pickNext, pickBox } from './setupLogic.js';

const MARK = { placed: '✓', next: '▶', todo: '·' };
const el = (id) => document.getElementById(id);

// ?setup: walk or fly to each hotspot from hotspots.md and press H to place it. Saves to public/site.json (dev server only).
export async function enableSetup({ app, site, player, rings, splat, camera, boxes }) {
  const panel = el('setup');
  panel.hidden = false;
  el('checklist').hidden = true;
  const say = (html) => { el('setup-body').innerHTML = html; };
  const esc = (t) => t.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

  let items = [];
  try {
    const res = await fetch('hotspots.md', { cache: 'no-store' });
    if (!res.ok) throw new Error('No public/hotspots.md yet. Create it (see README), then reload.');
    const parsed = parseHotspotsMd(await res.text());
    if (parsed.errors.length) throw new Error(`hotspots.md has problems:\n${parsed.errors.join('\n')}`);
    items = parsed.items;
  } catch (err) {
    say(`<p class="setup-error">${esc(err.message)}</p>`);
    return;
  }

  const dropped = unmatchedPlaced(items, site.hotspots);
  let placed = mergeHotspots(items, site.hotspots);
  const order = placed.map((h) => h.id); // undo stack
  placed.forEach((h) => rings.add(h));
  // Ring size for the next placement; [ and ] also resize the last ring placed.
  let radius = placed.at(-1)?.radius ?? 1.5;
  // , and . move the scan up and down to line its floor up with the rings (preview only; new-site --raise makes it stick).
  let raise = 0;
  // X deletes the red wall box under the crosshair (highlighted yellow); Z brings back the last one deleted.
  const removed = [];
  let target = -1;
  el('crosshair').hidden = false;
  app.on('update', () => {
    const f = camera.forward;
    const p = camera.getPosition();
    target = pickBox([p.x, p.y, p.z], [f.x, f.y, f.z], site.colliders);
    boxes?.highlight(site.colliders[target] ?? null);
  });
  const baseY = splat?.getLocalPosition().y ?? 0;
  // A renamed heading gets a new id, so its old position can't carry over: say so before the next save drops it.
  let message = dropped.length
    ? `Not in hotspots.md (renamed or removed), will be dropped when you place the next one: ${dropped.join(', ')}`
    : '';

  let currentId = null; // N and B move this; H places it
  const next = () => {
    currentId = pickNext(items, placed, currentId) ?? currentId;
    return items.find((it) => it.id === currentId && !placed.some((p) => p.id === it.id));
  };

  function render() {
    const n = next();
    const done = placed.length;
    const last = placed.find((p) => p.id === order.at(-1));
    const rows = queueRows(items, placed, n?.id)
      .map((r) => `<li class="q-${r.state}">${MARK[r.state]} ${esc(r.title)}</li>`).join('');
    say(`
      <p class="setup-next">${n ? `Place: <b>${esc(n.title)}</b>` : 'All placed'} <span>(${done} of ${items.length} placed)</span></p>
      <ol class="setup-list">${rows}</ol>
      <p class="setup-size">Ring size: <b>${radius.toFixed(2)} m</b> <span>${last ? `(also resizes ${esc(last.title)})` : ''}</span></p>
      ${raise ? `<p class="setup-size">Scan raised <b>${raise.toFixed(2)} m</b> <span>(preview) → rerun new-site with <b>--raise ${raise.toFixed(2)} --keep-hotspots</b></span></p>` : ''}
      ${removed.length ? `<p class="setup-size">Walls removed: <b>${removed.length}</b> <span>(Z puts the last one back)</span></p>` : ''}
      <p class="setup-keys">X delete the yellow box · Z undo delete · , . scan down / up (until the rings sit on the floor) · F fly · H place here · N next · B back · Backspace undo · [ ] ring size</p>
      ${message ? `<p class="setup-msg">${esc(message)}</p>` : ''}`);
  }

  async function save() {
    // Keep file order so the checklist matches hotspots.md.
    const hotspots = items.flatMap((it) => placed.filter((p) => p.id === it.id));
    const body = JSON.stringify({ hotspots, colliders: site.colliders });
    const res = await fetch('__save-site', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body });
    message = res.ok ? 'Saved' : `Not saved: ${await res.text()}`;
    if (res.ok) site.hotspots = hotspots;
    render();
  }

  app.keyboard.on(pc.EVENT_KEYDOWN, (e) => {
    if (e.key === pc.KEY_H) {
      const n = next();
      if (!n) return;
      const [x, , z] = player.getPosition();
      const h = { ...n, position: [+x.toFixed(2), 0, +z.toFixed(2)], radius };
      placed.push(h);
      order.push(h.id);
      rings.add(h);
      save();
    } else if (e.key === pc.KEY_N || e.key === pc.KEY_B) {
      currentId = pickNext(items, placed, currentId, e.key === pc.KEY_N ? 1 : -1) ?? currentId;
      message = '';
      render();
    } else if (e.key === pc.KEY_OPEN_BRACKET || e.key === pc.KEY_CLOSE_BRACKET) {
      radius = stepRadius(radius, e.key === pc.KEY_CLOSE_BRACKET ? 1 : -1);
      const i = placed.findIndex((p) => p.id === order.at(-1));
      if (i < 0) { render(); return; }
      placed[i] = { ...placed[i], radius };
      rings.remove(placed[i].id);
      rings.add(placed[i]);
      save();
    } else if ((e.key === pc.KEY_COMMA || e.key === pc.KEY_PERIOD) && splat) {
      raise = Math.round((raise + (e.key === pc.KEY_PERIOD ? 0.05 : -0.05)) * 100) / 100;
      const p = splat.getLocalPosition();
      splat.setLocalPosition(p.x, baseY + raise, p.z);
      render();
    } else if (e.key === pc.KEY_X) {
      if (target < 0) { message = 'Look at a red box first (it turns yellow).'; render(); return; }
      const [c] = site.colliders.splice(target, 1); // the player walks against this same list
      removed.push(c);
      boxes?.hide(c);
      save();
    } else if (e.key === pc.KEY_Z) {
      const c = removed.pop();
      if (!c) return;
      site.colliders.push(c);
      boxes?.show(c);
      save();
    } else if (e.key === pc.KEY_BACKSPACE) {
      const id = order.pop();
      if (!id) return;
      placed = placed.filter((p) => p.id !== id);
      rings.remove(id);
      currentId = id; // undone one is next again
      save();
    }
  });
  render();
}
