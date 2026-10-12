# Automatic Site Setup: Design

Date: 2026-10-11
Status: Approved in chat, pending written-spec review
Extends: `2026-10-10-hse-splat-induction-design.md`

## Goal

Go from a raw Gaussian-splat `.ply` to a walkable induction site with as
little manual work as possible:

1. One command turns the scan into a levelled, compressed splat, with walls,
   a floor and a start point, and writes `site.json`.
2. Hotspot text comes from a short description of the site. Claude Code
   writes it into `hotspots.md` with the user's normal plan, so no paid API
   is needed. A person reviews the text.
3. A setup mode in the app places each hotspot when the user flies to it and
   presses **H**. It saves straight into `site.json`.

## Decisions

| Topic | Decision |
|---|---|
| Hotspot text | Written by Claude Code (the session itself) from the user's description, saved as `hotspots.md`. No API key. A human reviews the text before use. |
| Hotspot positions | Placed by a person in `?setup` mode (fly, press H). About 5 minutes per site. |
| Levelling | Automatic, by detecting the floor. A printed report and `--up`/`--flip` flags allow correction. The SuperSplat "align to grid" method stays the manual fallback. |
| How levelling is applied | The splat file is not rewritten. `site.json` gets `splatRotation` (degrees) and a new `splatPosition` (metres), so the app turns and moves the splat at load. Colliders and hotspots use the levelled world coordinates. |
| Walls and floor | Generated from where splats are, on a 0.25 m grid, then merged into boxes. |
| Start point | The open floor cell nearest the middle of the scan, at least 0.6 m from any wall. |

## Command: `npm run new-site -- scan.ply [--up x|y|z] [--flip] [--box …] [--floaters]`

Steps (each is a pure, tested function in `scripts/`):

1. **Clean**: `cleanSplat` (existing, unchanged).
2. **Level** (`levelSplat` in `scripts/level.js`):
   - Use the clean, opaque, flat splats. A splat's normal is its shortest
     scale axis, rotated by its quaternion.
   - Cluster the normals into dominant directions, ignoring the sign of each
     normal, and weight each by the splat's flat area.
   - **Up** is the direction with the most flat area. In a room, that is
     floor plus ceiling.
   - `--up x|y|z` overrides the up axis of the scan.
   - **Sign**: up points away from the floor. The floor is the side with
     more splat mass in its first 1.2 m, because furniture sits on floors.
     `--flip` reverses it.
   - **Floor height**: the most common height among splats facing up, in
     the lowest third of the scan.
   - Output: a rotation that maps scan → world, with up = +Y; a translation
     that puts the floor at y = 0 and the scan centre at x = z = 0; and the
     levelled positions.
3. **Colliders** (`buildColliders` in `scripts/colliders.js`):
   - **Floor cells**: grid cells containing floor splats (y within ±0.15 m
     of 0).
   - **Solid cells**: cells with at least `minSolid` opaque splats between
     0.3 m and 1.8 m.
   - Merge each set into as few axis-aligned rectangles as possible (greedy
     row runs, then stacking).
   - Floor boxes are 0.2 m thick with their top at y = 0. Solid boxes run
     from y = 0 to y = 2.5.
   - Colliders cap: if more than 400 boxes come out, report it and grow the
     cell size until the count fits.
4. **Start**: `pickStart` picks the floor cell that is not solid, has at
   least 0.6 m clearance, and is nearest the scan centre. Yaw faces the
   longest open direction.
5. **Compress** (existing): `local-assets/site.sog`.
6. **Write `site.json`**: `splatUrl`, `splatRotation`, `splatPosition`,
   `start`, `colliders`, `hotspots: []`. It keeps an existing `hotspots`
   list, but only if the user passes `--keep-hotspots`.
7. **Report**: splat counts, the chosen up axis and how confident it is
   (the up direction's share of flat area), floor footprint in m², number
   of boxes, and the start point. If confidence is under 40%, print a
   warning that suggests `--up`/`--flip` or SuperSplat.

## Hotspot text: `hotspots.md`

The format is simple Markdown that a person can edit:

```markdown
## Card drop box
- Drop your visitor card here when you leave
- After 5 pm, cards must go in this box, not to reception

## Wellbeing room
- Quiet space for breaks and first aid recovery
- Ask reception for the key
```

Rules: each `##` heading is one hotspot title; the 2–3 `-` lines under it
are its points. The id is the slugged title. `parseHotspotsMd` validates
this and reports line numbers.

Claude Code writes this file from the user's description when asked
("write hotspots.md for: reception area, wellbeing room, card drop box —
cards dropped after 5 pm"). The README documents the prompt.

## Setup mode: `?setup`

- It loads `site.json` and `hotspots.md`.
- A panel lists the hotspots in the file and shows the next one without a
  position: **"Place: Card drop box (2 of 5)"**.
- **F** flies, as in debug.
- **H** places the current hotspot at the player's feet: x and z from the
  player, y = 0.
- **N** skips. **Backspace** removes the last placed hotspot.
- Placed hotspots show as rings straight away.
- Every change is saved by POSTing the whole updated `site.json` to a
  dev-only endpoint, `/__save-site`. A Vite plugin in `vite.config.js`
  writes it to `public/site.json`. The endpoint validates with
  `validateSite` before writing, and only exists under `npm run dev`.
- Hotspot text always comes from `hotspots.md`. Titles in `site.json` are
  refreshed from it on every save, so editing the text never needs a
  re-placement.

## App changes

- `site.json` gets an optional `splatPosition` (3 numbers). `scene.js`
  applies it with `splatRotation`.
- Validation allows an empty `hotspots` list.
- With 0 hotspots, the checklist panel shows "No hotspots yet".

## Error handling

- A PLY without scale or rotation properties: levelling falls back to
  `--up` (default y). A clear message names the missing properties.
- Low levelling confidence: a warning in the report (see above).
- No floor cells found: stop with "Couldn't find a floor. Try --up/--flip
  or level the scan in SuperSplat first."
- A broken `hotspots.md`: setup mode shows the parse error with its line
  number.
- A save that fails validation: setup mode shows the error, and nothing is
  written.

## Testing

Unit tests (Vitest, fake scans built in the tests):
- Levelling:
  - a Z-up room comes out Y-up
  - an upside-down room is flipped
  - a tilted room (20°) is levelled to within 2°
  - `--up`/`--flip` overrides work
  - the floor ends up at y = 0
- Colliders:
  - a 10 × 10 m room with 4 walls gives floor boxes and wall boxes in the
    right places
  - a 1 m doorway gap stays open
  - merging keeps the box count small (a straight wall is one box)
- `pickStart`: inside the room, 0.6 m or more from the walls, not inside
  any box.
- `parseHotspotsMd`:
  - valid file
  - missing points
  - 4 points
  - duplicate titles
  - errors include line numbers
- The save endpoint's validation: a pure function test.

Manual (on the user's Mac):
- Run `new-site` on the real reception scan. Check it comes out upright,
  you can walk it, and the walls stop you.
- Place hotspots in setup mode.

## Out of scope

- AI vision placement of hotspots (needs a paid API).
- Rotating the splat file itself.
- Multi-floor buildings.
- Sloped floors and ramps beyond the 30 cm step-up.
