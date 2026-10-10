# HSE Site Induction Walkthrough: Design

Date: 2026-10-10
Status: Approved in chat, pending written-spec review

## Goal

Site workers do their safety induction by walking a real scan of the site
in a laptop web browser. Hotspot rings on the floor teach hazards,
emergency exits and other HSE points. A checklist tracks which hotspots
they have found.

This extends the HSE site inspection app as a separate, standalone web app.
It does not share code or data with that app in version 1.

## Decisions

| Topic | Decision |
|---|---|
| Users | Site workers doing safety induction |
| Device | Laptop or desktop web browser only (Chrome, Edge, Safari). No phones. |
| Sites | One site. Hotspots and walls are set up by a developer. |
| Results | Nothing is saved. No login, no server, no database. |
| Objectives | Free roam. A checklist shows "N of M hotspots found". |
| Movement | First-person walking: WASD to move, mouse to look (pointer lock), Shift to walk faster, gravity. |
| Hotspot content | A text card: a title and 2–3 safety points. |
| Engine | PlayCanvas engine (npm library, code-first, no online editor), built with Vite. |
| Collision | Hand-placed invisible boxes for walls and floors, listed in `site.json`. |
| Source scan | One Gaussian splat `.ply`, about 500 MB. |

## Asset pipeline (manual, done once by a developer)

1. Open the `.ply` in SuperSplat (browser). Crop to the site and delete
   floaters, sky and noise.
2. Compress the cleaned file with SplatTransform (PlayCanvas CLI) into a
   web-ready splat format.
3. Target size: 150 MB or less. Smaller is better for loading on site wifi.
4. The compressed splat is **not committed to git** (GitHub rejects files
   over 100 MB). It is hosted at a URL (e.g. Cloudflare R2), and
   `site.json` stores that URL. For local development it lives in
   `local-assets/`, which is git-ignored.

Experiment, not part of version 1: run the cleaned splat through a
splat-to-mesh tool (e.g. IZUTSUYA 3DGS Mesh Converter) and compare the
mesh against hand-placed boxes as a collider.

## Architecture

A static website. `npm run build` outputs plain files that can be hosted
anywhere.

| Unit | Job | Depends on |
|---|---|---|
| `site.json` | All site data: splat URL, start position, collision boxes, hotspots (id, position, radius, title, points) | nothing |
| `siteData` | Loads `site.json` and checks it is valid; reports the exact field that is wrong | `site.json` |
| `scene` | Creates the PlayCanvas app, loads the splat, creates static collision boxes | `siteData` |
| `player` | First-person controller: pointer lock, WASD and mouse look, gravity, collision, reset to start if below the floor | `scene` |
| `hotspots` | Draws a glowing floor ring per hotspot. Detects when the player enters one and opens its text card. | `siteData`, `player` position |
| `checklist` | Tracks found hotspot ids, shows "N of M found", shows the "well done" screen when all are found | `hotspots` events |
| `ui` | Loading screen with progress, text card, checklist panel, done screen, error screens | — |
| `debug` | Enabled by `?debug`. Shows collision boxes in see-through red; **P** copies the player position to the clipboard. | `scene`, `player` |

Pure logic (`siteData` validation, hotspot hit test, `checklist` state) is
kept free of PlayCanvas so it can be unit tested without a browser.

### Data flow

`site.json` → `siteData` validates → `scene` builds the splat and boxes,
`hotspots` builds the rings → the player walks into a ring → the card
opens → `checklist` marks the hotspot found → once every hotspot is found,
the done screen shows.

### `site.json` shape

```json
{
  "splatUrl": "local-assets/site.sog",
  "start": { "position": [0, 1.7, 0], "yaw": 0 },
  "colliders": [
    { "position": [0, -0.5, 0], "size": [40, 1, 40] }
  ],
  "hotspots": [
    {
      "id": "fire-exit-north",
      "position": [12.4, 0, -3.1],
      "radius": 1.5,
      "title": "Emergency exit",
      "points": ["Keep this door clear at all times", "Assembly point is car park B"]
    }
  ]
}
```

## Error handling

1. A loading screen with a progress bar while the splat downloads.
2. No WebGL2: show "Please use Chrome, Edge or Safari" instead of a blank screen.
3. Invalid `site.json`: show which field is wrong (always in debug mode,
   a generic message otherwise).
4. Splat fails to download: show an error with a retry button.
5. Player falls below the floor: move them back to the start position.

## Testing

Automated (`npm test`, Vitest, no browser):
1. `site.json` validation: required fields, 2–3 points per hotspot,
   positive sizes and radii, unique hotspot ids.
2. Hotspot hit test: inside the radius counts, outside does not.
3. Checklist: entering a hotspot marks it once, repeat visits don't
   double-count, all found triggers done.

Manual release check (about 10 minutes, laptop):
1. Walk the whole site and confirm no wall can be passed through.
2. Visit every hotspot and read every card.
3. Reach the done screen.
4. Check in Chrome and Safari.

## Build order

Each step works on its own before the next starts.

1. Viewer: load and show the cleaned splat with a fly camera.
2. Walking: pointer-lock controller, gravity, collision boxes, debug mode.
3. Hotspot rings and text cards.
4. Checklist and done screen.
5. Loading screen and error handling.

## Out of scope for version 1

Phones and touch controls, VR, sound, multiple languages, minimap, saving
progress or results, quizzes, mesh colliders, more than one site, and an
editor for non-developers.
