const { test, expect } = require('@playwright/test');

test('settings cards pack without forced empty rows', async ({ page, viewport }, testInfo) => {
  await page.goto('/tests/ui/fixtures/config.html');
  await page.waitForTimeout(400);

  const grid = page.locator('.lar-config-masonry-grid');
  const sections = grid.locator('.config-section');
  await expect(grid).toBeVisible();
  await expect(sections).toHaveCount(6);

  const boxes = await sections.evaluateAll((nodes) => nodes.map((node) => {
    const rect = node.getBoundingClientRect();
    return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
  }));

  const width = viewport?.width || 0;
  if (width >= 1100) {
    expect(new Set(boxes.map((box) => Math.round(box.x))).size).toBe(2);
    expect(new Set(boxes.map((box) => Math.round(box.height))).size).toBeGreaterThan(1);

    for (const columnX of [...new Set(boxes.map((box) => Math.round(box.x)))]) {
      const column = boxes
        .filter((box) => Math.abs(box.x - columnX) < 3)
        .sort((a, b) => a.y - b.y);
      for (let index = 1; index < column.length; index += 1) {
        const gap = column[index].y - (column[index - 1].y + column[index - 1].height);
        expect(gap).toBeLessThanOrEqual(28);
      }
    }
  } else {
    expect(new Set(boxes.map((box) => Math.round(box.x))).size).toBe(1);
    for (let index = 1; index < boxes.length; index += 1) {
      expect(boxes[index].y).toBeGreaterThan(boxes[index - 1].y);
    }
  }

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth
  );
  expect(overflow).toBeLessThanOrEqual(1);

  await page.screenshot({
    path: testInfo.outputPath(`config-density-${testInfo.project.name}.png`),
    fullPage: true
  });
});
