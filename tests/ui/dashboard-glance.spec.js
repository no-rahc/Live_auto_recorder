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
  const statusChips = page.locator('.dash-autopill, .dash-v4-health, .dash-v4-updated');

  await expect(top).toBeVisible();
  await expect(overview.locator('.dash-v4-stat')).toHaveCount(4);
  await expect(page.locator('.dash-ver')).toHaveCount(0);
  await expect(system).toBeVisible();
  await expect(systemCards).toHaveCount(4);
  await expect(page.locator('.stor-vols')).toBeHidden();
  await expect(statusChips).toHaveCount(3);

  const chipBoxes = await statusChips.evaluateAll((nodes) => nodes.map((node) => {
    const rect = node.getBoundingClientRect();
    const style = getComputedStyle(node);
    return { height: rect.height, alignItems: style.alignItems, whiteSpace: style.whiteSpace };
  }));
  expect(new Set(chipBoxes.map((chip) => Math.round(chip.height))).size).toBe(1);
  expect(chipBoxes.every((chip) => chip.alignItems === 'center')).toBeTruthy();
  expect(chipBoxes.every((chip) => chip.whiteSpace === 'nowrap')).toBeTruthy();

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

    await page.evaluate(() => {
      const link = document.createElement('a');
      link.href = '/operations';
      link.className = 'restricted-menu ops-nav-link';
      link.textContent = '운영 관리';
      const nav = document.getElementById('mySidenav');
      nav.insertBefore(link, document.getElementById('user-info'));
    });

    const operationsLink = page.locator('.lar-sidebar-list a[href="/operations"]');
    await expect(operationsLink).toHaveCount(1);
    await expect(operationsLink).toHaveClass(/lar-sidebar-link/);
    await expect(operationsLink.locator('.lar-sidebar-link-copy strong')).toHaveText('운영 관리');
    await expect(page.locator('#mySidenav > a[href="/operations"]')).toHaveCount(0);

    const collapse = page.locator('[data-lar-sidebar-collapse]');
    await collapse.click();
    await expect(page.locator('body')).toHaveClass(/lar-sidebar-collapsed/);
    await expect(page.locator('.lar-sidebar-brand')).toBeHidden();
    await expect(page.locator('.lar-sidebar-link-copy').first()).toBeHidden();

    const collapsed = await page.evaluate(() => {
      const sidebar = document.querySelector('.sidenav').getBoundingClientRect();
      const list = document.querySelector('.lar-sidebar-list');
      const toggle = document.querySelector('[data-lar-sidebar-collapse]').getBoundingClientRect();
      const user = document.querySelector('.lar-sidebar-user').getBoundingClientRect();
      const logout = document.querySelector('.lar-sidebar-logout').getBoundingClientRect();
      const topbar = document.querySelector('.navbar-container').getBoundingClientRect();
      return {
        sidebarWidth: sidebar.width,
        toggleWidth: toggle.width,
        userWidth: user.width,
        logoutWidth: logout.width,
        logoutHeight: logout.height,
        listOverflow: list.scrollWidth - list.clientWidth,
        topbarX: topbar.x,
        rawTextVisible: Array.from(document.querySelectorAll('#mySidenav > a')).some((node) => {
          const style = getComputedStyle(node);
          return style.display !== 'none' && node.textContent.trim().length > 0;
        }),
      };
    });

    expect(collapsed.sidebarWidth).toBeGreaterThanOrEqual(70);
    expect(collapsed.sidebarWidth).toBeLessThanOrEqual(74);
    expect(collapsed.toggleWidth).toBe(40);
    expect(collapsed.userWidth).toBeLessThanOrEqual(50);
    expect(Math.abs(collapsed.logoutWidth - collapsed.logoutHeight)).toBeLessThanOrEqual(1);
    expect(collapsed.listOverflow).toBeLessThanOrEqual(1);
    expect(collapsed.topbarX).toBeGreaterThanOrEqual(70);
    expect(collapsed.rawTextVisible).toBeFalsy();

    await page.screenshot({
      path: testInfo.outputPath(`dashboard-collapsed-${testInfo.project.name}.png`),
      fullPage: true
    });

    await collapse.click();
    await expect(page.locator('body')).not.toHaveClass(/lar-sidebar-collapsed/);
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
