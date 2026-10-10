import { overlapIndex } from './collision.js';

const isVec3 = (v) => Array.isArray(v) && v.length === 3 && v.every(Number.isFinite);

export function validateSite(data) {
  const errors = [];
  const d = data && typeof data === 'object' ? data : {};

  if (typeof d.splatUrl !== 'string' || !d.splatUrl.trim()) errors.push('splatUrl: required text');
  if (d.splatRotation !== undefined && !isVec3(d.splatRotation)) errors.push('splatRotation: needs 3 numbers (degrees)');
  if (!isVec3(d.start?.position)) errors.push('start.position: needs 3 numbers');
  if (d.start?.yaw !== undefined && !Number.isFinite(d.start.yaw)) errors.push('start.yaw: must be a number');

  if (!Array.isArray(d.colliders)) errors.push('colliders: must be a list');
  else d.colliders.forEach((c, i) => {
    if (!isVec3(c?.position)) errors.push(`colliders[${i}].position: needs 3 numbers`);
    if (!isVec3(c?.size) || c.size.some((n) => n <= 0)) errors.push(`colliders[${i}].size: needs 3 numbers above 0`);
  });

  if (isVec3(d.start?.position) && Array.isArray(d.colliders) && !errors.some((e) => e.startsWith('colliders'))) {
    const hit = overlapIndex(d.start.position, d.colliders);
    if (hit >= 0) errors.push(`start.position: inside colliders[${hit}]`);
  }

  if (!Array.isArray(d.hotspots)) errors.push('hotspots: must be a list');
  else {
    const seen = new Set();
    d.hotspots.forEach((h, i) => {
      const at = `hotspots[${i}]`;
      if (typeof h?.id !== 'string' || !h.id.trim()) errors.push(`${at}.id: required text`);
      else if (seen.has(h.id)) errors.push(`${at}.id: duplicate id "${h.id}"`);
      else seen.add(h.id);
      if (!isVec3(h?.position)) errors.push(`${at}.position: needs 3 numbers`);
      if (!Number.isFinite(h?.radius) || h.radius <= 0) errors.push(`${at}.radius: must be above 0`);
      if (typeof h?.title !== 'string' || !h.title.trim()) errors.push(`${at}.title: required text`);
      const pts = h?.points;
      if (!Array.isArray(pts) || pts.length < 2 || pts.length > 3 || pts.some((p) => typeof p !== 'string' || !p.trim())) {
        errors.push(`${at}.points: needs 2-3 items of text`);
      }
    });
  }
  return errors;
}

export async function loadSite(url = 'site.json') {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Could not load ${url} (${res.status})`);
  let data;
  try {
    data = await res.json();
  } catch (err) {
    throw Object.assign(new Error(`${url} is not valid JSON: ${err.message}`), { invalidSite: true });
  }
  const errors = validateSite(data);
  if (errors.length) throw Object.assign(new Error(errors.join('\n')), { invalidSite: true });
  return data;
}
