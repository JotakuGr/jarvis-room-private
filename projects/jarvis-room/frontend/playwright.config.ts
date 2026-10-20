import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests', workers: 1, fullyParallel: false, timeout: 30_000,
  use: { baseURL: 'http://127.0.0.1:5174', viewport: { width: 1920, height: 1080 }, reducedMotion: 'reduce' },
  webServer: { command: 'npm run dev', url: 'http://127.0.0.1:5174', reuseExistingServer: !process.env.CI },
});
