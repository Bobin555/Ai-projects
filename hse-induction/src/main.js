import { loadSite } from './siteData.js';
import { createScene } from './scene.js';
import { createPlayer } from './player.js';
import { enableDebug } from './debug.js';
import { createHotspots } from './hotspots.js';
import { createChecklist } from './checklist.js';
import { enableSetup } from './setup.js';
import * as pc from 'playcanvas';
import { setLoading, showError, showCard, hideCard, renderChecklist, showDone } from './ui.js';

const canvas = document.getElementById('app');
const params = new URLSearchParams(location.search);
const setup = params.has('setup');
const debug = params.has('debug') || setup;

async function startScene(site) {
  setLoading(NaN);
  let scene;
  try {
    scene = await createScene(canvas, site, setLoading);
  } catch (err) {
    showError(debug && err.detail ? `${err.message}\n${err.detail}` : err.message, { retry: () => startScene(site) });
    return null;
  }
  setLoading(null);
  const player = createPlayer(scene.app, scene.camera, site, scene.colliders);
  const checklist = createChecklist(site.hotspots.map((h) => h.id));
  const refresh = () => renderChecklist(checklist.found(), checklist.total(),
    site.hotspots.map((h) => ({ title: h.title, found: checklist.isFound(h.id) })));
  refresh();
  const rings = createHotspots(scene.app, setup ? [] : site.hotspots, player.getPosition, {
    onEnter: (entered) => {
      if (setup) return; // placing hotspots isn't the induction: no checklist, no completion screen
      const wasComplete = checklist.isComplete();
      entered.forEach((h) => checklist.markFound(h.id));
      refresh();
      if (!wasComplete && checklist.isComplete()) {
        player.setPaused(true);
        showDone(() => player.setPaused(false));
      }
    },
    onNearestChange: (nearest) => (nearest ? showCard(nearest) : hideCard()),
  });
  scene.app.keyboard.on(pc.EVENT_KEYDOWN, (e) => { if (e.key === pc.KEY_E) hideCard(); });
  if (debug) enableDebug(scene.app, scene.colliders, player);
  if (setup) enableSetup({ app: scene.app, site, player, rings });
  const state = { ...scene, player, checklist };
  if (debug) window.__hse = state;
  return state;
}

async function boot() {
  if (!document.createElement('canvas').getContext('webgl2')) {
    showError('Please use Chrome, Edge or Safari');
    return;
  }
  let site;
  try {
    site = await loadSite();
  } catch (err) {
    showError(err.invalidSite && !debug ? 'Site data is invalid. Contact the site admin.' : err.message);
    return;
  }
  await startScene(site);
}

boot();
