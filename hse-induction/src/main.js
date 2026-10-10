import { loadSite } from './siteData.js';
import { createScene } from './scene.js';
import { createPlayer } from './player.js';
import { setLoading, showError } from './ui.js';

const canvas = document.getElementById('app');

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
    return { ...scene, player };
  } catch (err) {
    showError(err.message);
  }
}

const debug = new URLSearchParams(location.search).has('debug');
boot().then((state) => { if (debug && state) window.__hse = state; });
