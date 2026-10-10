# HSE Site Induction Walkthrough

Walk a Gaussian-splat scan of the site in a laptop browser, find the hotspot
rings, and read the HSE card at each one.

Design: `../docs/superpowers/specs/2026-10-10-hse-splat-induction-design.md`

## Run it

1. `npm install`
2. Put the cleaned, compressed splat at `local-assets/site.sog`. This folder
   is git-ignored, so the splat is never committed.
3. `npm run dev`, then open the address it prints in Chrome, Edge or Safari.
4. `npm test` runs the unit tests.

Add `?debug` to the address to see the collision boxes in red. Press **P**
to copy your position, then paste it into `public/site.json`. Press **F** to
fly through walls (Space up, C down) while you set up a new scan.

Look around by clicking the scene and moving the mouse, by dragging with a
mouse button held, or with the arrow keys.

## Prepare the splat (once per scan)

One command cleans and compresses a raw scan into `local-assets/site.sog`:

```
npm run clean-splat -- ~/Downloads/site.ply
```

It is deliberately careful. It only removes:
- splats too faint to see (below the threshold 3DGS training itself prunes at)
- far-away junk outside the main scan
- blobs wider than a tenth of the whole scan

Then it compresses the result. When it finishes it prints a report:

```
Splats:  2.10M → 1.95M
Removed: 40K invisible · 100K far-away · 2K huge blobs
Size:    500 MB → 90 MB
```

Options:
- `--box minX,minY,minZ,maxX,maxY,maxZ` keeps only what's inside your own box
  (use `?debug` and **P** in the app to find the corners).
- `--floaters` also removes floating specks, using SplatTransform's own filter
  (needs the Mac's GPU). Check the result: it can thin out glass and plants.
- `--out path.sog` writes the result somewhere else.
- `--keep-ply` also keeps the cleaned, uncompressed `.ply`.

If something your site needs gets removed, or junk is left behind, open the
`.ply` in SuperSplat (https://superspl.at/editor) and fix it by hand. Then
run the command on SuperSplat's export.

For a hosted build, upload `site.sog` to file hosting (e.g. Cloudflare R2)
and set `splatUrl` in `public/site.json` to its address.

## Site data (`public/site.json`)

- `splatUrl`: where the splat is loaded from.
- `splatRotation` (optional): turns the scan upright, in degrees `[x, y, z]`.
  Scans from nerfstudio/COLMAP are often Z-up: try `[-90, 0, 0]`, and if it's
  upside down, `[90, 0, 0]`.
- `start.position`: where the worker's feet start, as `[x, y, z]`. `start.yaw`
  is the direction they face, in degrees.
- `colliders`: invisible walls and floors. `position` is the box centre;
  `size` is its width, height and depth in metres.
- `hotspots`: `id` (unique), `position`, `radius` (metres), `title`, and
  2–3 `points`.
