import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests', workers: 1, fullyParallel: false, timeout: 30_000,
  use: { baseURL: 'http://127.0.0.1:15174', viewport: { width: 1920, height: 1080 }, reducedMotion: 'reduce', launchOptions: { args: ['--disable-gpu'] } },
  webServer: { command: './node_modules/.bin/vite --mode e2e --host 127.0.0.1 --port 15174 --strictPort', url: 'http://127.0.0.1:15174', reuseExistingServer: false },
});
