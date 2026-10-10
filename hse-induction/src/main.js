import { loadSite } from './siteData.js';
import { createScene } from './scene.js';
import { createPlayer } from './player.js';
import { enableDebug } from './debug.js';
import { setLoading, showError } from './ui.js';

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
    if (debug) enableDebug(scene.app, scene.colliders, player);
    return { ...scene, player };
  } catch (err) {
    showError(err.invalidSite && !debug ? 'Site data is invalid. Contact the site admin.' : err.message);
  }
}

boot().then((state) => { if (debug && state) window.__hse = state; });
