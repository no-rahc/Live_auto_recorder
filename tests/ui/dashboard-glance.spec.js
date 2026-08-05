const { test, expect } = require('@playwright/test');

test('dashboard prioritizes status in a compact glance layout', async ({ page, viewport }, testInfo) => {
  await page.goto('/tests/ui/fixtures/dashboard.html');
  await page.waitForTimeout(550);

  const top = page.locator('.dash-v5-top');
  const hero = page.locator('.dash-hero');
  const overview = page.locator('.dash-v4-overview');
  const dock = page.locator('.dash-dock');
  const system = page.locator('#sys-dashboard');
  const systemCards = page.locator('#sys-dashboard .dash-storage, #sys-dashboard .dash-meter');

  await expect(top).toBeVisible();
  await expect(overview.locator('.dash-v4-stat')).toHaveCount(4);
  await expect(page.locator('.dash-ver')).toHaveCount(0);
  await expect(system).toBeVisible();
  await expect(systemCards).toHaveCount(4);
  await expect(page.locator('.stor-vols')).toBeHidden();

  const width = viewport?.width || 0;
  const heroBox = await hero.boundingBox();
  const overviewBox = await overview.boundingBox();
  const dockBox = await dock.boundingBox();
  const cardBoxes = await systemCards.evaluateAll((nodes) => nodes.map((node) => {
    const rect = node.getBoundingClientRect();
    return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
  }));

  if (width >= 1100) {
    expect(Math.abs(heroBox.y - overviewBox.y)).toBeLessThan(4);
    expect(heroBox.height).toBeLessThanOrEqual(225);
    expect(overviewBox.height).toBeLessThanOrEqual(225);
    expect(dockBox.height).toBeLessThanOrEqual(100);
    expect(cardBoxes.every((card) => card.height <= 155)).toBeTruthy();

    if (width > 1180) {
      expect(new Set(cardBoxes.map((card) => Math.round(card.y))).size).toBe(1);
    }
  } else {
    expect(overviewBox.y).toBeGreaterThan(heroBox.y);
  }

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth
  );
  expect(overflow).toBeLessThanOrEqual(1);

  await page.screenshot({
    path: testInfo.outputPath(`dashboard-glance-${testInfo.project.name}.png`),
    fullPage: true
  });
});
