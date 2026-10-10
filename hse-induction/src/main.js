import { loadSite } from './siteData.js';
import { createScene } from './scene.js';
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
    return scene;
  } catch (err) {
    showError(err.message);
  }
}

boot();
