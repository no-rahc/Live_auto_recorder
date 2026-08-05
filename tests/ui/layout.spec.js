const { test, expect } = require('@playwright/test');

const fixture = '/tests/ui/fixtures/recording.html';

test('light layout has no horizontal overflow and visible content', async ({ page }, testInfo) => {
  await page.goto(fixture);
  await expect(page).toHaveTitle('Live Auto Recorder');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await expect(page.getByRole('heading', { name: '녹화 현황' })).toBeVisible();
  await expect(page.locator('.channel-info').first()).toBeVisible();
  await expect(page.locator('.channel-name').first()).toContainText('테스트 채널');

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);

  const bodyBackground = await page.locator('body').evaluate((node) => getComputedStyle(node).backgroundColor);
  expect(bodyBackground).toBe('rgb(247, 248, 250)');

  await page.screenshot({
    path: testInfo.outputPath(`recording-${testInfo.project.name}.png`),
    fullPage: true
  });
});

test('desktop proportions are bounded and sidebar is compact', async ({ page, viewport }) => {
  test.skip(!viewport || viewport.width < 1100, 'desktop-only proportion assertion');
  await page.goto(fixture);

  const sidebar = await page.locator('.sidenav').boundingBox();
  const content = await page.locator('#content').boundingBox();
  expect(sidebar.width).toBeGreaterThanOrEqual(240);
  expect(sidebar.width).toBeLessThanOrEqual(248);
  expect(content.width).toBeLessThanOrEqual(1241);
  expect(content.x).toBeGreaterThan(sidebar.width);

  const metricCards = page.locator('#sys-dashboard .tile');
  await expect(metricCards).toHaveCount(4);
  const first = await metricCards.nth(0).boundingBox();
  const last = await metricCards.nth(3).boundingBox();
  expect(Math.abs(first.width - last.width)).toBeLessThan(3);
});

test('responsive metrics and channel cards remain readable', async ({ page, viewport }) => {
  await page.goto(fixture);
  const metrics = page.locator('#sys-dashboard .tile');
  const first = await metrics.nth(0).boundingBox();
  const second = await metrics.nth(1).boundingBox();

  if (viewport.width <= 700) {
    expect(Math.abs(first.x - second.x)).toBeLessThan(2);
    expect(second.y).toBeGreaterThan(first.y);
  } else if (viewport.width <= 1320) {
    expect(Math.abs(first.y - second.y)).toBeLessThan(2);
  }

  const channels = page.locator('#channel-list > .channel');
  await expect(channels).toHaveCount(2);
  await expect(channels.nth(0).locator('.channel-info')).toBeVisible();
});
