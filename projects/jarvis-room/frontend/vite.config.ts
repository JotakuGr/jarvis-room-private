import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

const root = fileURLToPath(new URL('.', import.meta.url));
const canonical = ['room_devices.json', 'room_scenes.json'].map(name =>
  fileURLToPath(new URL(`../config/${name}`, import.meta.url)),
);
const headers = {
  'Permissions-Policy': 'microphone=(), camera=(), geolocation=()',
  'Referrer-Policy': 'no-referrer',
  'X-Content-Type-Options': 'nosniff',
};

export default defineConfig({
  plugins: [react()],
  cacheDir: 'node_modules/.vite-jarvis-room',
  optimizeDeps: {
    include: ['react', 'react-dom/client', '@react-three/fiber', 'three',
      'three/examples/jsm/postprocessing/EffectComposer.js',
      'three/examples/jsm/postprocessing/RenderPass.js',
      'three/examples/jsm/postprocessing/UnrealBloomPass.js',
      'three/examples/jsm/postprocessing/OutputPass.js'],
  },
  server: {
    host: '127.0.0.1', port: 5174, strictPort: true, cors: false, headers,
    fs: { strict: true, allow: [root, ...canonical], deny: ['.env', '.env.*', '**/.git/**', '**/secrets/**', '**/*.{pem,key}'] },
    proxy: {
      '^/api/presentation/events$': {
        target: 'http://127.0.0.1:8765', changeOrigin: true,
        rewrite: () => '/events',
      },
    },
  },
  preview: { host: '127.0.0.1', port: 5174, strictPort: true, headers },
  build: { outDir: 'dist', emptyOutDir: true, sourcemap: false,
  },
  test: { environment: 'node', include: ['src/**/*.test.ts', 'src/**/*.test.tsx'], maxWorkers: 1 },
});
