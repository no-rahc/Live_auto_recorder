const { test, expect } = require('@playwright/test');

test('operations console remains readable without horizontal overflow', async ({ page }, testInfo) => {
  await page.goto('/tests/ui/fixtures/operations.html');
  await expect(page).toHaveTitle('운영 관리');
  await expect(page.getByRole('heading', { name: '운영 관리' })).toBeVisible();
  await expect(page.locator('.ops-kpi')).toHaveCount(5);
  await expect(page.locator('.ops-storage-card')).toBeVisible();
  await expect(page.locator('.ops-health-card').first()).toContainText('테스트 채널');
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath(`operations-${testInfo.project.name}.png`), fullPage: true });
});

test('operations cards stack at mobile widths', async ({ page, viewport }) => {
  test.skip(!viewport || viewport.width > 760, 'mobile-only assertion');
  await page.goto('/tests/ui/fixtures/operations.html');
  const first = await page.locator('.ops-health-card').nth(0).boundingBox();
  const second = await page.locator('.ops-health-card').nth(1).boundingBox();
  expect(Math.abs(first.x - second.x)).toBeLessThan(3);
  expect(second.y).toBeGreaterThan(first.y);
});
