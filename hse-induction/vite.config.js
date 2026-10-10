import { writeFileSync } from 'node:fs';
import { checkSave } from './scripts/saveSite.js';

// Dev-only: setup mode (?setup) saves hotspot positions straight into public/site.json.
const saveSite = {
  name: 'save-site',
  apply: 'serve',
  configureServer(server) {
    server.middlewares.use('/__save-site', (req, res) => {
      if (req.method !== 'POST') { res.statusCode = 405; res.end(); return; }
      let body = '';
      req.on('data', (chunk) => { body += chunk; });
      req.on('end', () => {
        const r = checkSave(body);
        if (r.ok) writeFileSync(new URL('./public/site.json', import.meta.url), r.json);
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
