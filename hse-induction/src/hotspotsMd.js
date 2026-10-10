// hotspots.md: "## Title" then 2-3 "- point" lines per hotspot. Anything else is ignored.

export const slug = (title) => title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');

export function parseHotspotsMd(text) {
  const items = [];
  const errors = [];
  let current = null;
  const close = () => {
    if (!current) return;
    if (current.points.length < 2 || current.points.length > 3) {
      errors.push(`line ${current.line}: "${current.title}" needs 2-3 points (has ${current.points.length})`);
    }
    items.push({ id: current.id, title: current.title, points: current.points });
  };
  const seen = new Set();
  text.split(/\r?\n/).forEach((raw, i) => {
    const line = raw.trim();
    const heading = line.match(/^##\s+(.+)$/);
    const bullet = line.match(/^[-*]\s+(.+)$/);
    if (heading) {
      close();
      const title = heading[1].trim();
      const id = slug(title);
      if (seen.has(id)) errors.push(`line ${i + 1}: "${title}" is a duplicate title`);
      seen.add(id);
      current = { id, title, points: [], line: i + 1 };
    } else if (bullet && current) {
      current.points.push(bullet[1].trim());
    }
  });
  close();
  return { items, errors };
}

// Text always comes from the file; positions from what was already placed (matched by id).
export function mergeHotspots(items, placed) {
  const byId = new Map(placed.map((h) => [h.id, h]));
  return items.flatMap((it) => {
    const p = byId.get(it.id);
    return p ? [{ ...it, position: p.position, radius: p.radius }] : [];
  });
}
