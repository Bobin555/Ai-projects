import { writeFileSync, mkdirSync, rmSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { writePly } from './splatClean.js';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');

// Write the splat to `out` (.sog) with SplatTransform. -N drops NaN/Inf splats; -F (opt-in) drops floaters.
// Uses the GPU when there is one, otherwise the CPU (where --floaters isn't available).
export function compressSplat(splat, out, { floaters = false, keepPly = false } = {}) {
  mkdirSync(dirname(out), { recursive: true });
  const cleanedPly = `${out.replace(/\.[^.]+$/, '')}.cleaned.ply`;
  writeFileSync(cleanedPly, writePly(splat));
  const run = (extra, actions) => execFileSync(join(root, 'node_modules/.bin/splat-transform'), ['-w', ...extra, cleanedPly, '-N', ...actions, out], { stdio: 'pipe' });
  let floatersDone = floaters;
  try {
    run([], floaters ? ['-F'] : []);
  } catch {
    console.log('No usable GPU, compressing on the CPU instead (slower)…');
    if (floaters) console.log('  --floaters needs a GPU, so floaters were left in.');
    floatersDone = false;
    try {
      run(['-g', 'cpu'], []);
    } catch (err) {
      // SplatTransform prints its own reason on stderr; show just that, not Node's buffer dump.
      const reason = String(err.stderr ?? '').split('\n').find((l) => l.includes('✗')) ?? err.message.split('\n')[0];
      throw new Error(`Compression failed: ${reason.replace(/^\s*✗\s*/, '')}\nThe scan may be missing colour data (f_dc_0..2) or be corrupt.`);
    }
  }
  if (!keepPly) rmSync(cleanedPly);
  return { floatersDone, cleanedPly };
}
