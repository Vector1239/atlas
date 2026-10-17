import { defineConfig } from 'vite';
export default defineConfig({ base: './', server: { port: 4173, proxy: { '/api': 'http://127.0.0.1:4317' } }, build: { outDir: 'dist' } });
