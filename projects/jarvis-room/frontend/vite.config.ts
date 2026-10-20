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
  server: {
    host: '127.0.0.1', port: 5174, strictPort: true, cors: false, headers,
    fs: { strict: true, allow: [root, ...canonical], deny: ['.env', '.env.*', '**/.git/**', '**/secrets/**', '**/*.{pem,key}'] },
  },
  preview: { host: '127.0.0.1', port: 5174, strictPort: true, headers },
  build: { outDir: 'dist', emptyOutDir: true, sourcemap: false,
  },
  test: { environment: 'node', include: ['src/**/*.test.ts', 'src/**/*.test.tsx'], maxWorkers: 1 },
});
