const { test, expect } = require('@playwright/test');

async function expectNoHorizontalOverflow(page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
}

test('local mode removes account and logout controls from the sidebar', async ({ page }, testInfo) => {
  await page.goto('/tests/ui/fixtures/sidebar-account-local.html');
  await expect(page.locator('body')).toHaveClass(/lar-sidebar-account-clean/);
  await expect(page.locator('#user-info')).toHaveCount(0);
  await expect(page.locator('.lar-topbar-logout')).toHaveCount(0);
  await expect(page.locator('.lar-sidebar-list .lar-sidebar-link')).toHaveCount(2);
  await expectNoHorizontalOverflow(page);
  await page.screenshot({
    path: testInfo.outputPath(`sidebar-account-local-${testInfo.project.name}.png`),
    fullPage: true,
  });
});

test('authenticated mode keeps only a compact topbar logout action', async ({ page }, testInfo) => {
  await page.route('**/user_info', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ config: { loginMode: true } }),
  }));
  await page.goto('/tests/ui/fixtures/sidebar-account-auth.html');
  await expect(page.locator('body')).toHaveClass(/lar-sidebar-account-clean/);
  await expect(page.locator('#user-info')).toHaveCount(0);

  const logout = page.locator('.lar-topbar-logout');
  await expect(logout).toBeVisible();
  await expect(logout).toHaveAttribute('href', '/logout');
  await expect(logout).toHaveAccessibleName('로그아웃');

  const box = await logout.boundingBox();
  expect(box.width).toBeLessThanOrEqual(40);
  expect(box.height).toBeLessThanOrEqual(40);

  await expectNoHorizontalOverflow(page);
  await page.screenshot({
    path: testInfo.outputPath(`sidebar-account-auth-${testInfo.project.name}.png`),
    fullPage: true,
  });
});
