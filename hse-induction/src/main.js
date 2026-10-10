import { loadSite } from './siteData.js';
import { createScene } from './scene.js';
import { createPlayer } from './player.js';
import { enableDebug } from './debug.js';
import { createHotspots } from './hotspots.js';
import { createChecklist } from './checklist.js';
import * as pc from 'playcanvas';
import { setLoading, showError, showCard, hideCard, renderChecklist, showDone } from './ui.js';

const canvas = document.getElementById('app');
const debug = new URLSearchParams(location.search).has('debug');

async function boot() {
  if (!document.createElement('canvas').getContext('webgl2')) {
    showError('Please use Chrome, Edge or Safari');
    return;
  }
  try {
    const site = await loadSite();
    setLoading(NaN);
    const scene = await createScene(canvas, site, setLoading);
    setLoading(null);
    const player = createPlayer(scene.app, scene.camera, site, scene.colliders);
    const checklist = createChecklist(site.hotspots.map((h) => h.id));
    const refresh = () => renderChecklist(checklist.found(), checklist.total(),
      site.hotspots.map((h) => ({ title: h.title, found: checklist.isFound(h.id) })));
    refresh();
    createHotspots(scene.app, site.hotspots, player.getPosition, {
      onEnter: (entered) => {
        showCard(entered[0]);
        const wasComplete = checklist.isComplete();
        entered.forEach((h) => checklist.markFound(h.id));
        refresh();
        if (!wasComplete && checklist.isComplete()) showDone();
      },
      onLeaveAll: hideCard,
    });
    scene.app.keyboard.on(pc.EVENT_KEYDOWN, (e) => { if (e.key === pc.KEY_E) hideCard(); });
    if (debug) enableDebug(scene.app, scene.colliders, player);
    return { ...scene, player, checklist };
  } catch (err) {
    showError(err.invalidSite && !debug ? 'Site data is invalid. Contact the site admin.' : err.message);
  }
}

boot().then((state) => { if (debug && state) window.__hse = state; });
