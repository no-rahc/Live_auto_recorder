const { test, expect } = require('@playwright/test');

test.describe('local-only passwordless console', () => {
  test('removes login/account controls and keeps settings usable', async ({ page }) => {
    await page.goto('/tests/ui/fixtures/config.html');
    await page.addStyleTag({ url: '/templates/static/css/config-overview-v2.css' });
    await page.addStyleTag({ url: '/templates/static/css/local-mode-v1.css' });
    await page.addScriptTag({ url: '/templates/static/js/config-overview-v2.js' });
    await page.addScriptTag({ url: '/templates/static/js/local-mode-v1.js' });

    await expect(page.locator('.lar-local-mode-badge')).toHaveText('로컬 전용 · 로그인 없음');
    await expect(page.locator('#loginMode')).toHaveCount(0);
    await expect(page.locator('#account-fields')).toHaveCount(0);
    await expect(page.locator('[data-config-tab="security"]')).toHaveCount(0);
    await expect(page.locator('[data-config-panel="security"]')).toHaveCount(0);
    await expect(page.locator('.lar-config-tab')).toHaveCount(5);

    const localInput = page.locator('input[type="hidden"][name="loginMode"][data-lar-local-mode="true"]');
    await expect(localInput).toHaveValue('false');
    await expect(page.locator('[data-config-tab="files"] small')).toHaveText('접근 범위·운영');
    await expect(page.locator('[data-config-panel="files"] .lar-operations-link-card')).toHaveCount(1);

    const horizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
    expect(horizontalOverflow).toBe(false);
  });
});
