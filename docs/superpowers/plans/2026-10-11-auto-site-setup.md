# Automatic Site Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `npm run new-site -- scan.ply` produces a levelled, walkable site with auto walls, floor and start point; `?setup` mode places hotspots from `hotspots.md` with one key press each.

**Architecture:** Pure functions in `hse-induction/scripts/` (levelling, colliders, start) and `hse-induction/src/hotspotsMd.js` (shared with the browser), each unit-tested with fake scans. A thin CLI wires them to the existing cleanup and compression. Setup mode is a browser module, plus a dev-only Vite endpoint that validates and writes `public/site.json`.

**Tech Stack:** Node 22, Vite, PlayCanvas 2.23 (`pc.Quat`/`pc.Vec3` used in Node for rotation maths, so the conventions match the app), Vitest, SplatTransform.

**Spec:** `docs/superpowers/specs/2026-10-11-auto-site-setup-design.md`

## Global Constraints

- The splat file is never rotated. The level transform goes in `site.json` as `splatRotation` (degrees, applied with `entity.setEulerAngles`) and `splatPosition` (metres, applied with `entity.setPosition`). World = R·scan + t.
- World is Y-up, with the floor at y = 0. Grid cell is 0.25 m. "Solid" band is 0.3–1.8 m. Wall boxes run from y = 0 to 2.5. Floor boxes are 0.2 m thick with their top at 0.
- A PLY gaussian rotation is `rot_0..3 = (w, x, y, z)`. Scales are log-scale.
- No paid APIs. The save endpoint exists only under `vite` dev.
- `npm --prefix hse-induction test` stays green after every task.

## Review Focus

1. A scan whose up axis is a negative axis (e.g. −Z up): levelling must still produce +Y up. Test it in Task 2.
2. A scan with no scale or rotation properties (a plain point cloud): fall back to `--up`, and don't crash. Test it in Task 2.
3. A doorway narrower than one cell plus clearance: it must not be sealed by the box merge. Test a 1 m gap in Task 3.
4. Setup mode with `hotspots.md` edited after placing: text updates, and positions are kept by id. Test it in Task 4.
5. A save endpoint receiving invalid JSON or an invalid site: it must refuse, leaving the file untouched. Test it in Task 5.

---

### Task 1: App accepts `splatPosition` and an empty hotspot list

**Files:** Modify `src/siteData.js`, `src/scene.js`, `src/ui.js`; Test `test/siteData.test.js`

**Interfaces:**
- Produces: `site.splatPosition?: [x,y,z]` applied in `createScene`. `renderChecklist(0, 0, [])` shows "No hotspots yet".

- [ ] Tests: `splatPosition` is optional; 3 numbers pass; `[1,2]` gives an error containing `splatPosition`; `hotspots: []` is valid.
- [ ] Run → the `splatPosition` test FAILs.
- [ ] Implement the validation. `scene.js`: `if (site.splatPosition) splat.setPosition(...site.splatPosition)`. `renderChecklist` with total 0 shows `No hotspots yet`.
- [ ] Run → PASS. Commit `feat(hse-induction): splatPosition and empty hotspot list`.

### Task 2: `levelSplat`

**Files:** Create `scripts/level.js`; Test `test/level.test.js`

**Interfaces:**
- Consumes: `{ props, count, data }` (from `parsePly` / `cleanSplat`).
- Produces: `levelSplat(splat, { up?: 'x'|'y'|'z', flip?: boolean }) → { rotation: [rx,ry,rz] (deg, PlayCanvas Euler), position: [tx,ty,tz], positions: Float32Array (levelled xyz, 3 per splat), confidence: number 0..1, upAxisScan: [x,y,z] }`.

- [ ] Tests (fake rooms built in the test: floor, ceiling at 3 m, and 4 walls of flat splats with correct quaternions; furniture boxes on the floor):
  - a Y-up room: rotation ≈ identity, floor at y ≈ 0 (±0.05)
  - a Z-up room: levelled floor normal is +Y (dot > 0.999), floor y ≈ 0
  - a −Z-up room (upside down): +Y up
  - a room tilted 20° about X: levelled within 2°
  - `{ up: 'z' }` forces the axis; `{ flip: true }` reverses it
  - no rot or scale props: uses `up` (default `'y'`), confidence 0, no throw
  - centre: the levelled floor's x/z mean ≈ 0
- [ ] Run → FAIL.
- [ ] Implement:
  - Normal = quaternion-rotated axis of the smallest scale.
  - Flatness = smallest / middle scale < 0.3.
  - Area weight = product of the two largest scales.
  - Cluster with sign-agnostic bins: about 2000 normals sampled, greedy merge within 10°, area-weighted mean.
  - Up = the cluster with the most area; confidence = its share.
  - Sign: compare splat counts within 1.2 m of each extreme along up; the floor is the side with more.
  - Floor height = the mode (5 cm bins) of up-facing splats' heights in the lowest third.
  - Rotation = `pc.Quat` taking the up vector to +Y (shortest arc). Translate the floor to 0 and the x/z mean to 0.
- [ ] Run → PASS. Commit `feat(hse-induction): automatic scan levelling`.

### Task 3: `buildColliders` and `pickStart`

**Files:** Create `scripts/colliders.js`; Test `test/colliders.test.js`

**Interfaces:**
- Consumes: levelled `positions: Float32Array`, plus an opacity/size filter mask (opaque ≥ 0.3).
- Produces:
  - `buildColliders(positions, { cell = 0.25, minSolid = 8, maxBoxes = 400 }) → { colliders: Box[], floorCells: Set<string>, solidCells: Set<string>, cell }`
  - `pickStart({ floorCells, solidCells, cell }) → { position: [x,0,z], yaw }`
  - Box = `{ position, size }` (the site.json shape).

- [ ] Tests (a fake 10 × 10 m room: floor splats every 0.1 m, walls with a 1 m doorway gap in the north wall, a 1 × 1 m table):
  - every wall-band point lies inside some collider
  - the doorway centre at body height is inside no collider
  - the floor top is at y = 0 under the room
  - the straight south wall merges to ≤ 2 boxes
  - the table is solid
  - `pickStart` is not inside any collider (via `overlapIndex`), ≥ 0.6 m from solid cells, and inside the room
  - more than `maxBoxes` → the cell size grows until it fits
- [ ] Run → FAIL.
- [ ] Implement:
  - Count floor points per cell (|y| ≤ 0.15) and solid points per cell (0.3 ≤ y ≤ 1.8, count ≥ minSolid).
  - Merge: for each grid row (z), take runs of consecutive x cells; then stack identical runs across consecutive z rows into rectangles.
  - Floor rectangles become boxes `[cx, -0.1, cz]` with size `[w, 0.2, d]`. Solid rectangles become boxes `[cx, 1.25, cz]` with size `[w, 2.5, d]`.
  - `pickStart`: BFS distance from solid cells over floor cells; candidates with distance ≥ 0.6 m; the nearest to the floor centroid wins. Yaw faces the direction with the longest free ray (8 directions).
- [ ] Run → PASS. Commit `feat(hse-induction): auto colliders and start point`.

### Task 4: `parseHotspotsMd`

**Files:** Create `src/hotspotsMd.js`; Test `test/hotspotsMd.test.js`

**Interfaces:**
- Produces:
  - `parseHotspotsMd(text) → { items: [{ id, title, points }], errors: string[] }`, where errors are formatted `line N: …`
  - `slug(title) → id`
  - `mergeHotspots(items, placed: Hotspot[]) → Hotspot[]` keeps placed positions and radius by id, takes title and points from items, and drops placed ids missing from items

- [ ] Tests:
  - the spec's example parses to 2 items with the right points
  - a heading with 1 point → error containing `line`
  - 4 points → error
  - duplicate titles → error
  - text before the first heading is ignored
  - `slug('Card drop box') === 'card-drop-box'`
  - `mergeHotspots`: an edited title updates and keeps the position; a removed item is dropped
- [ ] Run → FAIL. Implement. Run → PASS. Commit `feat(hse-induction): hotspots.md parser`.

### Task 5: Save endpoint and setup mode

**Files:** Create `scripts/saveSite.js` (pure), `src/setup.js`; Modify `vite.config.js`, `src/main.js`, `index.html`, `src/style.css`, `src/hotspots.js` (add `addRing`/`removeRing`); Test `test/saveSite.test.js`

**Interfaces:**
- Produces:
  - `checkSave(body: string) → { ok: true, json: string } | { ok: false, error }`. It parses and runs `validateSite`; `json` is pretty-printed.
  - `createHotspots` returns `{ add(h), remove(id) }`.
- Consumes: `parseHotspotsMd`, `mergeHotspots` (Task 4), `player.getPosition`, `player.toggleFly`.

- [ ] Tests for `checkSave`: valid → ok, with 2-space JSON; non-JSON → `ok: false`; invalid site (bad hotspot) → `ok: false` with the validation message.
- [ ] Run → FAIL. Implement `checkSave`.
- [ ] Vite plugin (`apply: 'serve'`): `POST /__save-site` → `checkSave` → write `public/site.json`. Reply 200 or 400 with the error.
- [ ] `setup.js`, enabled by `?setup`:
  - fetch `hotspots.md` (404 → panel says to create it)
  - parse it and merge with `site.hotspots`
  - the panel shows `Place: <title> (k of n)` or `All placed`
  - **H** places at the player's x/z with y = 0 and radius 1.5, then saves
  - **N** skips; **Backspace** removes the last placed and saves
  - **F** flies (reuse `player.toggleFly`)
  - parse or save errors are shown in the panel
- [ ] E2E (headless): with an empty `site.json` and a 2-item `hotspots.md`, press H twice at two positions; `public/site.json` then has 2 hotspots with those positions; reload shows 2 rings and "0 of 2 found". Restore `site.json` afterwards.
- [ ] Commit `feat(hse-induction): setup mode places hotspots and saves site.json`.

### Task 6: `new-site` command and docs

**Files:** Create `scripts/new-site.mjs`; Modify `package.json`, `README.md`; delete nothing (`clean-splat` stays).

- [ ] Wire it: parse → `cleanSplat` → `levelSplat(clean, {up, flip})` → opacity mask → `buildColliders` → `pickStart` → write the cleaned ply → compress (reuse the GPU→CPU fallback) → write `public/site.json` (keep hotspots with `--keep-hotspots`) → report (the spec's list, including the confidence warning under 40%).
- [ ] "No floor" (zero floor cells) → exit 1 with the spec's message.
- [ ] E2E (here): a generated Z-up messy room (~200k splats with walls, a doorway and a table). Run `new-site`, then check `site.json` validates, the start is inside the room, and a headless walk forward stops at a wall. Screenshot.
- [ ] README: the new-site command, the flags, writing `hotspots.md` with Claude Code (with an example prompt), and setup-mode keys.
- [ ] Commit `feat(hse-induction): new-site command`. Push.
