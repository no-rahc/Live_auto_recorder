const { test, expect } = require('@playwright/test');

test('recording cards use a compact responsive grid and refresh active live metadata', async ({ page, viewport }, testInfo) => {
  let metadataRequests = 0;
  await page.route('**/api/update_metadata/*', async (route) => {
    metadataRequests += 1;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'success',
        from_cache: false,
        fresh: true,
        metadata: {
          status: 'OPEN',
          is_live: true,
          live_title: '실제 방송 제목',
          category: '라이브 토크',
        },
      }),
    });
  });

  await page.goto('/tests/ui/fixtures/recording.html');
  await page.waitForTimeout(550);

  const cards = page.locator('#channel-list > .channel');
  await expect(cards).toHaveCount(2);
  await expect(page.locator('#title-b')).toHaveText('실제 방송 제목');
  await expect(page.locator('#category-b')).toContainText('라이브 토크');
  expect(metadataRequests).toBeGreaterThanOrEqual(1);

  const first = await cards.nth(0).boundingBox();
  const second = await cards.nth(1).boundingBox();
  const thumbnail = await cards.nth(0).locator('.channel-thumbnail-container').boundingBox();

  expect(first).not.toBeNull();
  expect(second).not.toBeNull();
  expect(thumbnail).not.toBeNull();

  const width = viewport?.width || 0;
  if (width >= 1100) {
    expect(first.width).toBeLessThanOrEqual(430);
    expect(second.x).toBeGreaterThan(first.x + 20);
  } else if (width > 620) {
    expect(second.x).toBeGreaterThan(first.x + 20);
  } else {
    expect(Math.abs(first.x - second.x)).toBeLessThan(3);
    expect(second.y).toBeGreaterThan(first.y);
  }

  expect(thumbnail.height / thumbnail.width).toBeLessThanOrEqual(0.58);

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth
  );
  expect(overflow).toBeLessThanOrEqual(1);

  await page.screenshot({
    path: testInfo.outputPath(`recording-density-${testInfo.project.name}.png`),
    fullPage: true
  });
});
