import { defineConfig } from 'vite';
// `npm run dev` proxies to the service on ATLAS_PORT; start it with `backend.py --port 4317`.
const backend = `http://127.0.0.1:${process.env.ATLAS_PORT || 4317}`;
// The service only accepts its own Host and Origin, so the proxy presents those.
export default defineConfig({ base: './', server: { port: 4173, proxy: { '/api': { target: backend, changeOrigin: true, headers: { origin: backend } } } }, build: { outDir: 'dist' } });
