// Usage: npm run clean-splat -- <input.ply> [--box minX,minY,minZ,maxX,maxY,maxZ] [--floaters] [--out local-assets/site.sog] [--keep-ply]
import { readFileSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parsePly, cleanSplat } from './splatClean.js';
import { compressSplat } from './compress.js';

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

console.log('Compressing…');
const { floatersDone, cleanedPly } = compressSplat(splat, out, { floaters, keepPly });

const r = stats.removed;
console.log(`
Done in ${((Date.now() - t0) / 1000).toFixed(0)} s
  Splats:  ${fmt(stats.before)} → ${fmt(stats.after)}
  Removed: ${fmt(r.faint)} invisible · ${fmt(r.outside)} ${box ? 'outside --box' : 'far-away'} · ${fmt(r.huge)} huge blobs${floatersDone ? ' (+ floaters)' : ''}
  Size:    ${mb(statSync(input).size)} → ${mb(statSync(out).size)}
  Saved:   ${out}${keepPly ? `\n  Cleaned .ply kept: ${cleanedPly}` : ''}
`);
