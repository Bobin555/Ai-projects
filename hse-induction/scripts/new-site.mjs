// Usage: npm run new-site -- <scan.ply> [--up x|y|z|1|2|3] [--flip] [--box minX,minY,minZ,maxX,maxY,maxZ] [--floaters] [--keep-hotspots] [--raise metres]
// Raw scan → cleaned, levelled, compressed splat + public/site.json with walls, floor and a start point.
import { readFileSync, writeFileSync, statSync, existsSync } from 'node:fs';
import { dirname, join, resolve, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parsePly, cleanSplat } from './splatClean.js';
import { levelSplat } from './level.js';
import { buildColliders, pickStart } from './colliders.js';
import { compressSplat } from './compress.js';
import { validateSite } from '../src/siteData.js';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const flag = (name) => { const i = args.indexOf(name); return i >= 0 ? args.splice(i, 2)[1] : undefined; };
const takeFlag = (name) => args.includes(name) && args.splice(args.indexOf(name), 1).length > 0;
const flip = takeFlag('--flip');
const floaters = takeFlag('--floaters');
const keepHotspots = takeFlag('--keep-hotspots');
const diagnose = takeFlag('--diagnose');
const upArg = flag('--up');
const up = /^[123]$/.test(upArg ?? '') ? Number(upArg) : upArg;
const boxArg = flag('--box');
const raiseArg = flag('--raise');
const raise = raiseArg === undefined ? 0 : Number(raiseArg);
const input = args[0];
const fail = (msg) => { console.error(msg); process.exit(1); };

if (!input) fail('Usage: npm run new-site -- <scan.ply> [--up x|y|z|1|2|3] [--flip] [--box minX,minY,minZ,maxX,maxY,maxZ] [--floaters] [--keep-hotspots] [--raise metres]');
if (up && !['x', 'y', 'z', 1, 2, 3].includes(up)) fail('--up must be x, y, z, or a candidate number 1-3 from the report');
if (!Number.isFinite(raise) || Math.abs(raise) > 3) fail('--raise needs a number of metres, e.g. --raise 0.3 (from the ?setup panel)');
const box = boxArg ? boxArg.split(',').map(Number) : null;
if (box && (box.length !== 6 || box.some((n) => !Number.isFinite(n)))) fail('--box needs 6 numbers: minX,minY,minZ,maxX,maxY,maxZ');

const out = join(root, 'local-assets/site.sog');
const siteFile = join(root, 'public/site.json');
const mb = (bytes) => `${(bytes / 1e6).toFixed(0)} MB`;
const fmt = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(2)}M` : n.toLocaleString());
const round = (a, d = 2) => a.map((v) => +v.toFixed(d));
const t0 = Date.now();
{
  let st;
  try { st = statSync(input); } catch { console.error(`File not found: ${input}\nTip: drag the .ply file from Finder into Terminal to paste its exact path.`); process.exit(1); }
  if (!st.isFile()) { console.error(`That's a folder, not a .ply file: ${input}\nTip: drag the .ply file itself from Finder into Terminal.`); process.exit(1); }
}

console.log(`Reading ${input} (${mb(statSync(input).size)})…`);
const { splat, stats } = cleanSplat(parsePly(readFileSync(input)), { box });

console.log('Levelling…');
const level = levelSplat(splat, { up, flip });
if (raise) {
  // The floor was found too high (raise > 0, the view looks too tall) or too low: move the scan so the real floor sits at y = 0.
  for (let n = 1; n < level.positions.length; n += 3) level.positions[n] += raise;
  level.position[1] += raise;
  level.roomHeight += raise;
}
if (level.missingProps.length) {
  console.log(`  This scan has no orientation data (missing ${level.missingProps.join(', ')}),
  so it can't find "up" by itself. Using --up ${typeof up === 'string' ? up : 'y'}; check the result looks upright.`);
}

// Walls and floor come from solid-looking splats only: faint ones are haze, not surfaces.
const oi = splat.props.indexOf('opacity');
const solid = [];
for (let n = 0; n < splat.count; n++) {
  if (oi >= 0 && 1 / (1 + Math.exp(-splat.data[n * splat.props.length + oi])) < 0.3) continue;
  solid.push(level.positions[n * 3], level.positions[n * 3 + 1], level.positions[n * 3 + 2]);
}
console.log('Building walls and floor…');
const grid = buildColliders(Float32Array.from(solid));
if (!grid.floorCells.size) fail("Couldn't find a floor. Try --up/--flip, or level the scan in SuperSplat first.");
const start = pickStart(grid);
if (diagnose || !start) printDiagnosis(Float32Array.from(solid), grid);
const candidateList = () => level.candidates
  .map((c, i) => `      --up ${i + 1}: [${round(c.direction).join(', ')}] ${Math.round(c.share * 100)}% of flat surfaces${i === 0 && !up ? ' (used this time)' : ''}`)
  .join('\n');
if (!start) {
  fail(`Couldn't find open floor to start on. The room measures ${level.roomHeight.toFixed(1)} m floor to ceiling.
  - Most likely "up" was picked wrong (a wall instead of the floor). Try the other candidates:
${candidateList()}
    and add --flip if the result is upside down.
  - If every candidate fails and the height is far from 2-5 m, the scan isn't in metres: rescale it in SuperSplat first.`);
}

console.log('Compressing…');
let floatersDone;
try {
  ({ floatersDone } = compressSplat(splat, out, { floaters }));
} catch (err) {
  fail(err.message);
}

let previous = {};
if (keepHotspots && existsSync(siteFile)) {
  try { previous = JSON.parse(readFileSync(siteFile, 'utf8')); } catch { console.log('  Existing site.json is unreadable, so no hotspots were kept.'); }
}
const site = {
  splatUrl: relative(root, out).split('\\').join('/'),
  splatRotation: round(level.rotation, 3),
  splatPosition: round(level.position, 3),
  start: { position: round(start.position), yaw: Math.round(start.yaw) },
  colliders: grid.colliders.map((c) => ({ position: round(c.position, 3), size: round(c.size, 3) })),
  hotspots: keepHotspots && Array.isArray(previous.hotspots) ? previous.hotspots : [],
};
const errors = validateSite(site);
if (errors.length) fail(`Generated site.json is invalid (please report this):\n${errors.join('\n')}`);
writeFileSync(siteFile, `${JSON.stringify(site, null, 2)}\n`);

const r = stats.removed;
const floorArea = grid.floorCells.size * grid.cell * grid.cell;
const confidence = Math.round(level.confidence * 100);
const typedAxis = typeof up === 'string';
console.log(`
Done in ${((Date.now() - t0) / 1000).toFixed(0)} s
  Splats:   ${fmt(stats.before)} → ${fmt(stats.after)} (removed ${fmt(r.faint)} invisible · ${fmt(r.outside)} far-away · ${fmt(r.huge)} huge${floatersDone ? ' · floaters' : ''})
  Up:       scan axis [${round(level.upAxisScan).join(', ')}]${up ? ` (--up ${up})` : ''}${flip ? ' (flipped)' : ''} · confidence ${typedAxis ? 'n/a' : `${confidence}%`}
  Room:     ${level.roomHeight.toFixed(1)} m floor to ceiling
  Floor:    ${floorArea.toFixed(0)} m² · ${grid.colliders.length} collision boxes (${grid.cell.toFixed(2)} m grid)
  Start:    [${site.start.position.join(', ')}] facing ${site.start.yaw}°
  Hotspots: ${site.hotspots.length ? `${site.hotspots.length} kept` : 'none yet — write public/hotspots.md, then open ?setup'}
  Size:     ${mb(statSync(input).size)} → ${mb(statSync(out).size)}
  Saved:    ${out}
            ${siteFile}`);
if (!up && (confidence < 40 || level.ambiguous)) {
  const list = candidateList();
  console.log(`
  ⚠ Not sure which way is up${level.ambiguous ? ' (two directions are close; long corridors do this)' : ''}.
    Candidates:
${list}
    If the room looks sideways, rerun with the next one; if upside down, add --flip.`);
}
if (level.roomHeight < 2 || level.roomHeight > 5) {
  console.log(`
  ⚠ The room measures ${level.roomHeight.toFixed(1)} m floor to ceiling. If that's wrong, the scan isn't in metres
    (nerfstudio often shrinks scenes): rescale it in SuperSplat, then rerun.`);
}

// What the tool "sees": where splats sit in height, and how much of the floor plan is open vs solid.
function printDiagnosis(pts, g) {
  const bins = new Map();
  for (let n = 1; n < pts.length; n += 3) {
    const b = Math.floor(pts[n] / 0.25);
    if (b >= -4 && b < 24) bins.set(b, (bins.get(b) ?? 0) + 1);
  }
  const max = Math.max(...bins.values());
  console.log('\n  Diagnosis — splats by height above the detected floor (each row 25 cm):');
  for (let b = 23; b >= -4; b--) {
    const c = bins.get(b) ?? 0;
    console.log(`    ${(b * 0.25).toFixed(2).padStart(5)} m ${'#'.repeat(Math.round((c / max) * 40)).padEnd(40)} ${c}`);
  }
  const band = new Map();
  for (let n = 0; n < pts.length; n += 3) {
    const y = pts[n + 1];
    if (y < 0.3 || y > 1.8) continue;
    const k = `${Math.floor(pts[n] / g.cell)},${Math.floor(pts[n + 2] / g.cell)}`;
    band.set(k, (band.get(k) ?? 0) + 1);
  }
  const counts = [...band.values()].sort((a, b) => a - b);
  const pct = (p) => counts[Math.floor(p * (counts.length - 1))] ?? 0;
  const free = [...g.floorCells].filter((c) => !g.solidCells.has(c)).length;
  console.log(`
  Grid ${g.cell.toFixed(2)} m · floor cells ${g.floorCells.size} · solid cells ${g.solidCells.size} · open floor cells ${free}
  Splats per cell at body height (0.3–1.8 m): median ${pct(0.5)}, 90% ${pct(0.9)}, 99% ${pct(0.99)} (solid threshold ${Math.round(g.threshold)})`);
}
