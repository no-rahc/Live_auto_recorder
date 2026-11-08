import { defineConfig } from '@playwright/test';

const realApp = process.env.UI_REAL_APP === '1';
const port = realApp ? 4175 : 4174;
export default defineConfig({
  testDir: './tests/browser',
  testMatch: realApp ? '**/real-app.spec.ts' : ['**/preview.spec.ts', '**/ui.spec.ts'],
  outputDir: realApp ? 'test-results/real-app' : 'test-results/fixture',
  reporter: [['list'], ['html', { outputFolder: realApp ? 'playwright-report/real-app' : 'playwright-report/fixture', open: 'never' }]],
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    headless: true,
    timezoneId: 'UTC',
    locale: 'ko-KR',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE },
  },
  webServer: {
    command: `python3 tests/${realApp ? 'serve_real_app' : 'serve_ui'}.py`,
    url: `http://127.0.0.1:${port}${realApp ? '/healthz' : '/'}`,
    reuseExistingServer: !process.env.CI,
    timeout: realApp ? 120000 : 30000,
  },
  timeout: 30000,
  retries: 0,
});
