const { test, expect } = require('@playwright/test');

const fixture = '/tests/ui/fixtures/config-overview.html';

test('settings are summarized across six focused tabs', async ({ page }) => {
  await page.goto(fixture);

  await expect(page.locator('.lar-config-tab')).toHaveCount(6);
  await expect(page.getByRole('tab', { name: /파일 관리/ })).toBeVisible();
  await expect(page.getByRole('tab', { name: /접속 보안/ })).toBeVisible();
  await expect(page.locator("[data-config-tab='basic'] .lar-tab-status")).toHaveText('자동 녹화 ON');
  await expect(page.locator("[data-config-tab='processing'] .lar-tab-status")).toHaveText('원본 유지');
  await expect(page.locator("[data-config-tab='notifications'] .lar-tab-status")).toHaveText('1개 연결');
  await expect(page.locator("[data-config-tab='files'] .lar-tab-status")).toHaveText('안전');
  await expect(page.locator("[data-config-tab='security'] .lar-tab-status")).toHaveText('로그인 ON');

  await expect(page.locator('.lar-config-overview-line')).toContainText('로그인 보호');
  await expect(page.locator('.lar-setting-switch').first()).toBeVisible();
});

test('boolean switch uses compact stable proportions', async ({ page }) => {
  await page.goto(fixture);
  const control = page.locator('.lar-setting-switch').first();
  const track = control.locator('.lar-switch-track');

  const before = await control.boundingBox();
  const trackBox = await track.boundingBox();
  expect(before).not.toBeNull();
  expect(trackBox).not.toBeNull();
  expect(before.width).toBeGreaterThanOrEqual(86);
  expect(before.width).toBeLessThanOrEqual(92);
  expect(before.height).toBeGreaterThanOrEqual(34);
  expect(before.height).toBeLessThanOrEqual(38);
  expect(Math.abs(trackBox.width - 34)).toBeLessThan(0.1);
  expect(Math.abs(trackBox.height - 20)).toBeLessThan(0.1);

  await control.click();
  const after = await control.boundingBox();
  expect(after).not.toBeNull();
  expect(Math.abs(after.width - before.width)).toBeLessThan(0.1);
  expect(Math.abs(after.height - before.height)).toBeLessThan(0.1);
});

test('encoding keeps the common choice visible and advanced fields collapsed', async ({ page }) => {
  await page.goto(fixture);
  await page.getByRole('tab', { name: /후처리·인코딩/ }).click();

  await expect(page.locator('.lar-encoding-current')).toContainText('원본 유지');
  const advanced = page.locator('.lar-encoding-advanced');
  await expect(advanced).not.toHaveAttribute('open', '');
  await advanced.locator('summary').click();
  await expect(advanced).toHaveAttribute('open', '');
  await expect(page.locator('#video_codec')).toBeAttached();
});

test('switch changes update the tab state and show before-after values', async ({ page }) => {
  await page.goto(fixture);
  await page.waitForTimeout(250);

  await page.locator(".lar-setting-switch[aria-labelledby='lar-label-autoRecordingMode']").click();
  await expect(page.locator("[data-config-tab='basic'] .lar-tab-status")).toHaveText('수동 녹화');

  const details = page.locator('.lar-config-change-details');
  await expect(details).toBeVisible();
  await expect(details).toContainText('자동 녹화');
  await expect(details).toContainText('ON');
  await expect(details).toContainText('OFF');
});

test('settings layout does not create page-level horizontal overflow', async ({ page }) => {
  await page.goto(fixture);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
