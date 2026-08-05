const { test, expect } = require('@playwright/test');

test('operations controls use clear hierarchy and accessible tab states', async ({ page, viewport }, testInfo) => {
  await page.goto('/tests/ui/fixtures/operations-controls.html');

  const storageTab = page.locator('[data-ops-tab="storage"]');
  const healthTab = page.locator('[data-ops-tab="health"]');
  const storagePanel = page.locator('[data-ops-panel="storage"]');
  await expect(storageTab).toHaveCSS('background-color', 'rgb(255, 242, 232)');
  await expect(storageTab).toHaveCSS('color', 'rgb(232, 95, 0)');
  await expect(healthTab).not.toHaveCSS('background-color', 'rgb(255, 111, 15)');
  await expect(healthTab).toHaveAttribute('aria-selected', 'false');
  await expect(storagePanel).toBeVisible();
  await expect(storagePanel).toHaveAttribute('aria-hidden', 'false');

  const refresh = page.locator('#ops-refresh');
  await expect(refresh).toHaveCSS('background-color', 'rgb(255, 255, 255)');
  await expect(refresh).not.toHaveCSS('color', 'rgb(255, 255, 255)');

  const primary = page.locator('.ops-action-primary');
  const secondary = page.locator('#ops-cleanup-preview');
  const danger = page.locator('#ops-cleanup-run');
  await expect(primary).toHaveCSS('background-color', 'rgb(255, 111, 15)');
  await expect(secondary).toHaveCSS('background-color', 'rgb(255, 255, 255)');
  await expect(danger).toBeDisabled();

  await healthTab.click();
  await expect(healthTab).toHaveAttribute('aria-selected', 'true');
  await expect(storageTab).toHaveAttribute('aria-selected', 'false');
  await expect(page.locator('[data-ops-panel="health"]')).toBeVisible();
  await expect(storagePanel).toBeHidden();

  await healthTab.focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.locator('[data-ops-tab="jobs"]')).toBeFocused();
  await expect(page.locator('[data-ops-tab="jobs"]')).toHaveAttribute('aria-selected', 'true');
  await expect(page.locator('[data-ops-panel="jobs"]')).toBeVisible();

  await storageTab.click();
  await expect(storagePanel).toBeVisible();
  await expect(storagePanel).toHaveAttribute('aria-hidden', 'false');
  await page.locator('#ops-cleanup-result').evaluate((node) => {
    node.innerHTML = '<div class="ops-cleanup-box"><strong>삭제 대상 2개 · 8.4 GB</strong></div>';
  });
  await expect(danger).toBeEnabled();
  await expect(danger).toHaveAttribute('aria-disabled', 'false');

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);

  if ((viewport?.width || 0) > 900) {
    const actionGroup = await page.locator('.ops-action-group').boundingBox();
    const dangerZone = await page.locator('.ops-danger-zone').boundingBox();
    expect(dangerZone.x).toBeGreaterThan(actionGroup.x + actionGroup.width);
  }

  await page.mouse.move(0, 0);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: testInfo.outputPath(`operations-controls-${testInfo.project.name}.png`),
    fullPage: true,
  });
});
