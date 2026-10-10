# HSE Splat Induction Walkthrough Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A laptop web app where a site worker walks a Gaussian-splat scan of one site, finds hotspot rings, and reads HSE text cards while a checklist tracks progress.

**Architecture:** A static Vite site in `hse-induction/`, using the PlayCanvas engine to render the splat. All site data lives in `site.json`. The pure logic (validation, AABB collision, hotspot hit test, checklist) sits in PlayCanvas-free modules tested with Vitest. Thin PlayCanvas and DOM modules wire it together.

**Tech Stack:** Node 20+, Vite, PlayCanvas engine (npm `playcanvas`, v2), Vitest, plain JavaScript (ES modules).

**Spec:** `docs/superpowers/specs/2026-10-10-hse-splat-induction-design.md`

## Global Constraints

- Laptop or desktop only (Chrome, Edge, Safari). No touch controls and no phone layout.
- Requires WebGL2. Without it, show exactly: `Please use Chrome, Edge or Safari`.
- No backend, no login, no saved progress. `npm run build` outputs static files.
- The splat file is never committed. `local-assets/` is git-ignored, and `site.json.splatUrl` points at the splat.
- Controls: WASD to move, mouse to look (click the canvas to lock the pointer, Esc to release), Shift to walk faster.
- Each hotspot has 2–3 `points`, and hotspot ids are unique.
- `?debug` in the URL turns on debug mode: red see-through boxes, and **P** copies the player position.
- Collision uses axis-aligned boxes only: `{ position: [x,y,z], size: [w,h,d] }`, where position is the box centre. Collision is our own pure AABB code; no physics engine.
- If the player falls below `start.position[1] - 20`, put them back at `start`.

## Review Focus

1. **Tab switched away and back:** the first frame's `dt` can be seconds long, which lets the player tunnel through walls. Clamp `dt` to 0.05 s. Test in Task 3.
2. **Standing still inside a ring:** the card must open once per entry, not every frame. Leaving and re-entering may open it again. Test in Task 5.
3. **Two overlapping rings:** both count as found; the card shows the nearest one. Test in Task 5.
4. **Splat URL returns 404 or a CORS error:** show the error screen with Retry, not a blank page. Test in Task 7 (manual check, with a broken `splatUrl`).
5. **Pressing Esc to read a card:** the pointer unlocks. The card stays readable, and clicking the canvas resumes walking. Test in Task 5 (manual check).

---

## File Structure

```
hse-induction/
  package.json, vite.config.js, index.html, .gitignore, README.md
  public/site.json            # site data (sample values until the real site is set up)
  src/main.js                 # boot: WebGL2 check, load data, build scene, start loop
  src/siteData.js             # validateSite(data) -> errors[]   (pure)
  src/collision.js            # moveWithCollision(...)            (pure)
  src/hotspotLogic.js         # nearestHotspotInside(...)         (pure)
  src/checklist.js            # createChecklist(ids)              (pure)
  src/scene.js                # PlayCanvas app, splat, collider boxes
  src/player.js               # pointer lock, WASD/mouse, gravity, uses collision.js
  src/hotspots.js             # ring entities, enter detection, uses hotspotLogic.js
  src/debug.js                # ?debug overlays and P-to-copy
  src/ui.js                   # DOM: loading, card, checklist, done, error screens
  src/style.css
  test/*.test.js
```

---

### Task 1: Project scaffold and `site.json` validation

**Files:**
- Create: `hse-induction/package.json`, `vite.config.js`, `index.html`, `.gitignore`, `README.md`, `public/site.json`, `src/siteData.js`
- Test: `hse-induction/test/siteData.test.js`

**Interfaces:**
- Produces: `validateSite(data: object): string[]`, which returns a list of human-readable errors, each naming the path, e.g. `"hotspots[2].points: needs 2-3 items"`. An empty array means the data is valid.
- Produces: `loadSite(url = 'site.json'): Promise<object>`. It fetches the file, runs `validateSite`, and throws `Error` with the errors joined by `\n` if any.

- [ ] **Step 1: Scaffold.** `npm create vite@latest hse-induction -- --template vanilla`, then delete the template demo files. `npm i playcanvas` and `npm i -D vitest`. Add scripts `dev`, `build`, `test: "vitest run"`. Add `local-assets/` to `.gitignore`. Set `vite.config.js` `server.fs.allow` to include `local-assets`.
- [ ] **Step 2: Write `public/site.json`** using the exact shape from the spec. Use `"splatUrl": "local-assets/site.sog"`, one floor collider `[0,-0.5,0]` size `[40,1,40]`, and two sample hotspots (`fire-exit-north`, `chemical-store`) with 2 points each.
- [ ] **Step 3: Write failing tests** in `test/siteData.test.js`:
  - the sample `public/site.json` → `[]`
  - `splatUrl` missing → an error containing `splatUrl`
  - `start.position` not 3 numbers → an error containing `start.position`
  - collider `size` with 0 or a negative number → an error containing `colliders[0].size`
  - a hotspot with 1 point, and one with 4 points → an error containing `hotspots[0].points`
  - a hotspot with `radius <= 0` → an error containing `radius`
  - two hotspots sharing an id → an error containing `duplicate id`
  - an empty `title` → an error containing `title`
- [ ] **Step 4: Run** `npm test`. Expected: FAIL (validateSite not defined).
- [ ] **Step 5: Implement `validateSite` and `loadSite`** in `src/siteData.js`. Collect every error rather than stopping at the first one.
- [ ] **Step 6: Run** `npm test`. Expected: all PASS.
- [ ] **Step 7: Write the README.** Cover the setup (`npm i`, `npm run dev`), where to put the splat (`local-assets/site.sog`), and the SuperSplat → SplatTransform pipeline from the spec.
- [ ] **Step 8: Commit** `feat(hse-induction): scaffold and site.json validation`.

---

### Task 2: Splat viewer

**Files:**
- Create: `src/main.js`, `src/scene.js`, `src/ui.js` (just `showError(message, {retry})` and `setLoading(fraction|null)`), `src/style.css`

**Interfaces:**
- Consumes: `loadSite()` (Task 1).
- Produces: `createScene(canvas, site, onProgress): Promise<{ app, camera }>`. It creates a `pc.Application` that fills the window and resizes with it, loads `site.splatUrl` as a `gsplat` asset on an entity, and places the camera at `site.start`. It rejects if the asset fails to load.
- Produces: `ui.showError(message: string, opts?: { retry?: () => void })` and `ui.setLoading(fraction: number | null)` (`null` hides the loading screen).

- [ ] **Step 1: Implement `main.js`.** If `!document.createElement('canvas').getContext('webgl2')`, call `showError('Please use Chrome, Edge or Safari')` and stop. Otherwise `loadSite()` → `createScene()`. Any rejection goes to `showError(err.message)`.
- [ ] **Step 2: Implement `createScene`.** Use `pc.Asset(name, 'gsplat', { url })`, `app.assets.load`, and `entity.addComponent('gsplat', { asset })`. Set `pc.FILLMODE_FILL_WINDOW` and `pc.RESOLUTION_AUTO`.
- [ ] **Step 3: Manual check.** Put any splat at `local-assets/site.sog` (the cleaned site, or a PlayCanvas sample splat) and run `npm run dev`. Expected: the splat is visible from the start position.
- [ ] **Step 4: Manual check.** Set `splatUrl` to `missing.sog`. Expected: an error screen, not a blank page.
- [ ] **Step 5: Commit** `feat(hse-induction): load and render site splat`.

---

### Task 3: Walking with collision

**Files:**
- Create: `src/collision.js`, `src/player.js`
- Modify: `src/scene.js` (build the colliders), `src/main.js` (start the player)
- Test: `test/collision.test.js`

**Interfaces:**
- Produces: `moveWithCollision(pos: [x,y,z], vel: [x,y,z], dt: number, boxes: Box[], radius = 0.3, height = 1.7): { pos: [x,y,z], vel: [x,y,z], grounded: boolean }`. The player is an upright box of half-width `radius` and the given `height`, with its feet at `pos[1]`. It resolves the X, then Y, then Z axis separately. It clamps `dt` to `0.05`. If a vertical hit stops the player, it sets `vel[1] = 0`, and `grounded` is true when they landed on top of a box.
- Produces: `createPlayer(app, camera, site): { update(dt), getPosition(): [x,y,z], resetToStart() }`. Speed is 1.4 m/s walking and 3 m/s with Shift, gravity is −9.8 m/s², and the camera sits at `pos + [0, 1.6, 0]`.
- Produces: `scene.colliders: Box[]`, taken straight from `site.colliders`.

- [ ] **Step 1: Write failing tests:**
  - standing on the floor box with zero velocity → y stays the same and `grounded === true`
  - walking at +x into a wall box → x stops at `wall.minX - radius`, and z movement still applies (sliding along walls)
  - falling from y=5 onto the floor → lands on the floor top with `vel[1] === 0`
  - `dt = 2` at speed 10 toward a 0.2 m thick wall 1 m away → does **not** pass through (because of the dt clamp)
  - no boxes → position just integrates the velocity
- [ ] **Step 2: Run** `npm test`. Expected: FAIL.
- [ ] **Step 3: Implement `moveWithCollision`.** It's pure, with no PlayCanvas imports.
- [ ] **Step 4: Run** `npm test`. Expected: PASS.
- [ ] **Step 5: Implement `createPlayer`.** Clicking the canvas calls `requestPointerLock()`. Mouse movement changes yaw and pitch only while locked, with pitch clamped to ±85°. WASD is relative to yaw. If `y < start.y - 20`, call `resetToStart()`. Register it with `app.on('update', dt => player.update(dt))`.
- [ ] **Step 6: Manual check.** Add 2 test wall boxes to `site.json`. Expected: you can walk, you can't pass through either wall, and you slide along them. Delete the floor box → you fall and respawn at the start.
- [ ] **Step 7: Commit** `feat(hse-induction): first-person walking with box collision`.

---

### Task 4: Debug mode

**Files:**
- Create: `src/debug.js`
- Modify: `src/main.js`

**Interfaces:**
- Consumes: `scene.colliders`, `player.getPosition()`.
- Produces: `enableDebug(app, colliders, player)`. It is called only when `new URLSearchParams(location.search).has('debug')`.

- [ ] **Step 1: Implement `enableDebug`.** Add one `box` render entity per collider, using a red unlit material at opacity 0.3. Pressing **P** writes `JSON.stringify(position rounded to 2 decimals)` to `navigator.clipboard` and shows a 1.5 s toast reading `Copied [x, y, z]`.
- [ ] **Step 2: Make validation errors visible.** When `loadSite` throws and debug is on, `showError` shows the full multi-line message. Without debug, it shows `Site data is invalid. Contact the site admin.`
- [ ] **Step 3: Manual check.** Open `?debug` and expect red boxes. Press P and paste: the coordinates appear. Break a hotspot in `site.json` and expect the exact field error in debug mode and the generic message without it.
- [ ] **Step 4: Commit** `feat(hse-induction): debug overlays and position copy`.

---

### Task 5: Hotspot rings and text cards

**Files:**
- Create: `src/hotspotLogic.js`, `src/hotspots.js`
- Modify: `src/ui.js` (add `showCard(hotspot)` and `hideCard()`), `src/main.js`
- Test: `test/hotspotLogic.test.js`

**Interfaces:**
- Produces: `hotspotsInside(pos: [x,y,z], hotspots): Hotspot[]`. It returns every hotspot whose horizontal (x,z) distance is ≤ `radius`, sorted nearest first. Height is ignored.
- Produces: `createHotspots(app, site.hotspots, getPlayerPos, onEnter: (hotspot) => void)`. It draws a glowing ring on the floor at each position, using a torus or flat cylinder with an emissive material and a slow pulse. Each frame it compares the ids inside against the previous frame and calls `onEnter` only for ids that are newly inside.

- [ ] **Step 1: Write failing tests** for `hotspotsInside`:
  - exactly on the radius → inside
  - 0.01 past the radius → outside
  - a big height difference but horizontally inside → inside
  - two overlapping hotspots → both are returned, nearest first
- [ ] **Step 2: Write a failing test** for the enter logic, extracted as a pure helper `newlyEntered(prevIds: Set, nowIds: Set): string[]` in `hotspotLogic.js`:
  - the same set on two frames → `[]`
  - leaving then re-entering → the id is returned again
- [ ] **Step 3: Run** `npm test`. Expected: FAIL.
- [ ] **Step 4: Implement** `hotspotsInside`, `newlyEntered` and `createHotspots`.
- [ ] **Step 5: Run** `npm test`. Expected: PASS.
- [ ] **Step 6: Implement the card.** `showCard` displays the title and a bullet list of `points` in a panel on the right side, so walking continues while it's open. It closes when the player leaves the ring or presses **E**.
- [ ] **Step 7: Manual check.** Walk into a ring and the card opens once. Stand still and it doesn't flicker. Press Esc: the card stays readable, and clicking the canvas resumes walking.
- [ ] **Step 8: Commit** `feat(hse-induction): hotspot rings and HSE cards`.

---

### Task 6: Checklist and done screen

**Files:**
- Create: `src/checklist.js`
- Modify: `src/ui.js` (add `renderChecklist(found, total, items)` and `showDone()`), `src/main.js`
- Test: `test/checklist.test.js`

**Interfaces:**
- Produces: `createChecklist(ids: string[]): { markFound(id): boolean, found(): number, total(): number, isComplete(): boolean, isFound(id): boolean }`. `markFound` returns `true` only the first time an id is marked, and ignores unknown ids by returning `false`.
- Consumes: `onEnter` from Task 5. Every hotspot that's newly entered (not just the nearest one) is marked.

- [ ] **Step 1: Write failing tests:**
  - starts at 0 of N
  - `markFound('a')` twice → returns true then false, and `found() === 1`
  - an unknown id → false, and the count is unchanged
  - all ids marked → `isComplete() === true`
- [ ] **Step 2: Run** `npm test`. Expected: FAIL.
- [ ] **Step 3: Implement `createChecklist`.**
- [ ] **Step 4: Run** `npm test`. Expected: PASS.
- [ ] **Step 5: Wire it up.** Show a top-left panel reading `3 of 8 found`, with the hotspot titles listed and found ones ticked. When the list is complete, `showDone()` displays `Induction walkthrough complete` with a **Keep exploring** button that closes it.
- [ ] **Step 6: Manual check.** Visit every sample hotspot: the count goes up once each, and the done screen appears after the last one.
- [ ] **Step 7: Commit** `feat(hse-induction): hotspot checklist and completion screen`.

---

### Task 7: Loading screen and error handling

**Files:**
- Modify: `src/scene.js` (report progress), `src/ui.js`, `src/main.js`

**Interfaces:**
- Consumes: `createScene(..., onProgress)` and `ui.setLoading` from Task 2.

- [ ] **Step 1: Report progress.** Use the asset's `progress` event if the engine version emits it for gsplat; otherwise wrap the splat in a `fetch` stream that counts bytes against `Content-Length`. Show `Loading site… 42%`, or an indeterminate bar if there's no length.
- [ ] **Step 2: Add Retry.** When the splat fails to load (404, CORS or network), call `showError('Could not load the site scan.', { retry })`. Retry re-runs `createScene` without reloading the page.
- [ ] **Step 3: Manual check (Review Focus 4).** Set `splatUrl` to a missing file: the error and Retry appear. Fix the URL, click Retry, and the scene loads.
- [ ] **Step 4: Manual check.** Throttle the connection to "Fast 4G" in Chrome DevTools. Expected: the percentage rises, then the loading screen disappears.
- [ ] **Step 5: Final verification.** `npm test` all pass. `npm run build` succeeds. `npx vite preview` with the real splat completes the manual release check in the spec (walls, every card, the done screen, Chrome and Safari).
- [ ] **Step 6: Commit** `feat(hse-induction): loading progress and retry on failure`.
