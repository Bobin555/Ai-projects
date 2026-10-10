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

1. Open the raw `.ply` in SuperSplat (https://superspl.at/editor). Crop to
   the site, and delete floaters, sky and noise. Export a `.ply`.
2. Compress it with SplatTransform:
   `npx @playcanvas/splat-transform cleaned.ply local-assets/site.sog`
3. Aim for 150 MB or less.

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
