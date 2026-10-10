// Usage: npm run clean-splat -- <input.ply> [--box minX,minY,minZ,maxX,maxY,maxZ] [--floaters] [--out local-assets/site.sog] [--keep-ply]
import { readFileSync, writeFileSync, statSync, mkdirSync, rmSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parsePly, writePly, cleanSplat } from './splatClean.js';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const flag = (name) => { const i = args.indexOf(name); return i >= 0 ? args.splice(i, 2)[1] : undefined; };
const takeFlag = (name) => args.includes(name) && args.splice(args.indexOf(name), 1).length > 0;
const keepPly = takeFlag('--keep-ply');
const floaters = takeFlag('--floaters');
const boxArg = flag('--box');
const out = resolve(flag('--out') ?? join(root, 'local-assets/site.sog'));
const input = args[0];

if (!input) {
  console.error('Usage: npm run clean-splat -- <input.ply> [--box minX,minY,minZ,maxX,maxY,maxZ] [--floaters] [--out file.sog] [--keep-ply]');
  process.exit(1);
}
const box = boxArg ? boxArg.split(',').map(Number) : null;
if (box && (box.length !== 6 || box.some((n) => !Number.isFinite(n)))) {
  console.error('--box needs 6 numbers: minX,minY,minZ,maxX,maxY,maxZ');
  process.exit(1);
}

const mb = (bytes) => `${(bytes / 1e6).toFixed(0)} MB`;
const fmt = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(2)}M` : n.toLocaleString());
const t0 = Date.now();

console.log(`Reading ${input} (${mb(statSync(input).size)})…`);
const { splat, stats } = cleanSplat(parsePly(readFileSync(input)), { box });

mkdirSync(dirname(out), { recursive: true });
const cleanedPly = out.replace(/\.[^.]+$/, '') + '.cleaned.ply';
writeFileSync(cleanedPly, writePly(splat));

console.log('Compressing…');
// -N drops splats with NaN/Inf values; -F (opt-in) drops splats that don't add to any solid surface.
// Both run inside SplatTransform. Uses the GPU when there is one.
const compress = (extra, actions) => execFileSync(join(root, 'node_modules/.bin/splat-transform'), ['-w', ...extra, cleanedPly, '-N', ...actions, out], { stdio: 'pipe' });
let floatersDone = floaters;
try {
  compress([], floaters ? ['-F'] : []);
} catch {
  console.log('No usable GPU, compressing on the CPU instead (slower)…');
  if (floaters) console.log('  --floaters needs a GPU, so floaters were left in.');
  floatersDone = false;
  compress(['-g', 'cpu'], []);
}
if (!keepPly) rmSync(cleanedPly);

const r = stats.removed;
console.log(`
Done in ${((Date.now() - t0) / 1000).toFixed(0)} s
  Splats:  ${fmt(stats.before)} → ${fmt(stats.after)}
  Removed: ${fmt(r.faint)} invisible · ${fmt(r.outside)} ${box ? 'outside --box' : 'far-away'} · ${fmt(r.huge)} huge blobs${floatersDone ? ' (+ floaters)' : ''}
  Size:    ${mb(statSync(input).size)} → ${mb(statSync(out).size)}
  Saved:   ${out}${keepPly ? `\n  Cleaned .ply kept: ${cleanedPly}` : ''}
`);
