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
to copy your position, then paste it into `public/site.json`.

## Prepare the splat (once per scan)

One command cleans and compresses a raw scan into `local-assets/site.sog`:

```
npm run clean-splat -- ~/Downloads/site.ply
```

It removes near-invisible haze, giant blurry blobs, far-away junk and
floaters, then compresses the result. When it finishes it prints a report:

```
Splats:  2.10M → 1.40M
Removed: 210K faint · 12K huge blobs · 300K far-away · 180K floaters
Size:    500 MB → 62 MB
```

Options:
- `--box minX,minY,minZ,maxX,maxY,maxZ` keeps only what's inside your own box
  (use `?debug` and **P** in the app to find the corners).
- `--out path.sog` writes the result somewhere else.
- `--keep-ply` also keeps the cleaned, uncompressed `.ply`.

If something your site needs gets removed, or junk is left behind, open the
`.ply` in SuperSplat (https://superspl.at/editor) and fix it by hand. Then
run the command on SuperSplat's export.

For a hosted build, upload `site.sog` to file hosting (e.g. Cloudflare R2)
and set `splatUrl` in `public/site.json` to its address.

## Site data (`public/site.json`)

- `splatUrl`: where the splat is loaded from.
- `start.position`: where the worker's feet start, as `[x, y, z]`. `start.yaw`
  is the direction they face, in degrees.
- `colliders`: invisible walls and floors. `position` is the box centre;
  `size` is its width, height and depth in metres.
- `hotspots`: `id` (unique), `position`, `radius` (metres), `title`, and
  2–3 `points`.
