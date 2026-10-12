import * as pc from 'playcanvas';

// Rejects if the splat can't be loaded (404, CORS, bad file).
export function createScene(canvas, site, onProgress = () => {}) {
  const app = new pc.Application(canvas, {
    mouse: new pc.Mouse(document.body),
    keyboard: new pc.Keyboard(window),
    graphicsDeviceOptions: { antialias: false },
  });
  app.setCanvasFillMode(pc.FILLMODE_FILL_WINDOW);
  app.setCanvasResolution(pc.RESOLUTION_AUTO);
  const onResize = () => app.resizeCanvas();
  window.addEventListener('resize', onResize);
  app.on('destroy', () => window.removeEventListener('resize', onResize));

  const camera = new pc.Entity('camera');
  camera.addComponent('camera', { clearColor: new pc.Color(0.05, 0.06, 0.08), nearClip: 0.05, farClip: 500 });
  const [x, y, z] = site.start.position;
  camera.setPosition(x, y + 1.6, z);
  camera.setEulerAngles(0, site.start.yaw ?? 0, 0);
  app.root.addChild(camera);

  return new Promise((resolve, reject) => {
    const asset = new pc.Asset('site-splat', 'gsplat', { url: site.splatUrl });
    asset.on('progress', (received, total) => onProgress(total ? received / total : NaN));
    asset.once('load', () => {
      const splat = new pc.Entity('splat');
      splat.addComponent('gsplat', { asset });
      // Scans often come out Z-up or flipped; site.json can turn and move them so the floor is level at y = 0.
      if (site.splatRotation) splat.setEulerAngles(...site.splatRotation);
      if (site.splatPosition) splat.setPosition(...site.splatPosition);
      app.root.addChild(splat);
      app.start();
      resolve({ app, camera, splat, colliders: site.colliders });
    });
    asset.once("error", (err) => { setTimeout(() => app.destroy()); reject(Object.assign(new Error(`Could not load the site scan (${site.splatUrl}).`), { detail: String(err) })); });
    app.assets.add(asset);
    app.assets.load(asset);
  });
}
