import { it, expect } from 'vitest';
import config from '../vite.config.js';

it('builds with relative asset paths so the site works from any folder', () => {
  expect(config.base).toBe('./');
});
