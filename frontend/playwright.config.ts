import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests/browser',
  use: { baseURL: 'http://127.0.0.1:4174', headless: true, launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE } },
  webServer: { command: 'python3 tests/serve_ui.py', url: 'http://127.0.0.1:4174/v2', reuseExistingServer: !process.env.CI },
  timeout: 30000, retries: 0,
});
