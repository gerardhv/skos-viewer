import { defineConfig } from 'astro/config';
import react from '@astrojs/react';

// GitHub project pages: https://{user}.github.io/{repo}/
const base = process.env.ASTRO_BASE || '/begrippenkader-corporatiesector/';

export default defineConfig({
  site: process.env.ASTRO_SITE || 'https://aedes-datastandaarden.github.io',
  base,
  trailingSlash: 'always',
  integrations: [react()],
  output: 'static',
});
