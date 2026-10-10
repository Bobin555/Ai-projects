import { loadSite } from './siteData.js';
import { createScene } from './scene.js';
import { createPlayer } from './player.js';
import { enableDebug } from './debug.js';
import { createHotspots } from './hotspots.js';
import * as pc from 'playcanvas';
import { setLoading, showError, showCard, hideCard } from './ui.js';

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
    createHotspots(scene.app, site.hotspots, player.getPosition, {
      onEnter: (entered) => showCard(entered[0]),
      onLeaveAll: hideCard,
    });
    scene.app.keyboard.on(pc.EVENT_KEYDOWN, (e) => { if (e.key === pc.KEY_E) hideCard(); });
    if (debug) enableDebug(scene.app, scene.colliders, player);
    return { ...scene, player };
  } catch (err) {
    showError(err.invalidSite && !debug ? 'Site data is invalid. Contact the site admin.' : err.message);
  }
}

boot().then((state) => { if (debug && state) window.__hse = state; });
