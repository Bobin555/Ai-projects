import * as pc from 'playcanvas';
import { parseHotspotsMd, mergeHotspots, unmatchedPlaced } from './hotspotsMd.js';
import { queueRows, stepRadius } from './setupLogic.js';

const MARK = { placed: '✓', next: '▶', skipped: '↷', todo: '·' };
const el = (id) => document.getElementById(id);

// ?setup: walk or fly to each hotspot from hotspots.md and press H to place it. Saves to public/site.json (dev server only).
export async function enableSetup({ app, site, player, rings }) {
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
  let skipped = new Set();
  // Ring size for the next placement; [ and ] also resize the last ring placed.
  let radius = placed.at(-1)?.radius ?? 1.5;
  // A renamed heading gets a new id, so its old position can't carry over: say so before the next save drops it.
  let message = dropped.length
    ? `Not in hotspots.md (renamed or removed), will be dropped when you place the next one: ${dropped.join(', ')}`
    : '';

  const next = () => items.find((it) => !placed.some((p) => p.id === it.id) && !skipped.has(it.id));

  function render() {
    const n = next();
    const done = placed.length;
    const last = placed.find((p) => p.id === order.at(-1));
    const rows = queueRows(items, placed, skipped, n?.id)
      .map((r) => `<li class="q-${r.state}">${MARK[r.state]} ${esc(r.title)}</li>`).join('');
    say(`
      <p class="setup-next">${n ? `Place: <b>${esc(n.title)}</b>` : 'All placed'} <span>(${done} of ${items.length} placed)</span></p>
      <ol class="setup-list">${rows}</ol>
      <p class="setup-size">Ring size: <b>${radius.toFixed(2)} m</b> <span>${last ? `(also resizes ${esc(last.title)})` : ''}</span></p>
      <p class="setup-keys">F fly · H place here · N skip · Backspace undo · [ ] ring size</p>
      ${message ? `<p class="setup-msg">${esc(message)}</p>` : ''}`);
  }

  async function save() {
    // Keep file order so the checklist matches hotspots.md.
    const hotspots = items.flatMap((it) => placed.filter((p) => p.id === it.id));
    const body = JSON.stringify({ hotspots });
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
    } else if (e.key === pc.KEY_N) {
      const n = next();
      if (n) skipped.add(n.id);
      if (!next()) skipped = new Set(); // wrap around to anything still unplaced
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
    } else if (e.key === pc.KEY_BACKSPACE) {
      const id = order.pop();
      if (!id) return;
      placed = placed.filter((p) => p.id !== id);
      rings.remove(id);
      skipped.delete(id);
      save();
    }
  });
  render();
}
