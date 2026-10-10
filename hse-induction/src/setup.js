import * as pc from 'playcanvas';
import { parseHotspotsMd, mergeHotspots } from './hotspotsMd.js';

const RADIUS = 1.5;
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

  let placed = mergeHotspots(items, site.hotspots);
  const order = placed.map((h) => h.id); // undo stack
  placed.forEach((h) => rings.add(h));
  let skipped = new Set();
  let message = '';

  const next = () => items.find((it) => !placed.some((p) => p.id === it.id) && !skipped.has(it.id));

  function render() {
    const n = next();
    const done = placed.length;
    say(`
      <p class="setup-next">${n ? `Place: <b>${esc(n.title)}</b>` : 'All placed'} <span>(${done} of ${items.length} placed)</span></p>
      <p class="setup-keys">F fly · H place here · N skip · Backspace undo</p>
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
      const h = { ...n, position: [+x.toFixed(2), 0, +z.toFixed(2)], radius: RADIUS };
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
