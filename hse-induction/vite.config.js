import { readFileSync, writeFileSync } from 'node:fs';
import { checkSave } from './scripts/saveSite.js';

// Dev-only: setup mode (?setup) saves hotspot positions straight into public/site.json.
const saveSite = {
  name: 'save-site',
  apply: 'serve',
  configureServer(server) {
    server.middlewares.use('/__save-site', (req, res) => {
      if (req.method !== 'POST') { res.statusCode = 405; res.end(); return; }
      // JSON only: browsers must preflight a cross-site JSON POST, and Vite refuses it, so other pages can't write here.
      if (!String(req.headers['content-type']).startsWith('application/json')) { res.statusCode = 415; res.end('JSON only'); return; }
      let body = '';
      req.on('data', (chunk) => { body += chunk; if (body.length > 1e6) req.destroy(); });
      req.on('end', () => {
        const file = new URL('./public/site.json', import.meta.url);
        const r = checkSave(body, JSON.parse(readFileSync(file, 'utf8')));
        if (r.ok) writeFileSync(file, r.json);
        res.statusCode = r.ok ? 200 : 400;
        res.end(r.ok ? 'saved' : r.error);
      });
    });
  },
};

export default {
  base: './',
  plugins: [saveSite],
};
