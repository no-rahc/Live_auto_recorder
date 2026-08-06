const { test, expect } = require('@playwright/test');

async function loadRefinement(page, withScript = true) {
  await page.addStyleTag({ url: '/templates/static/css/ui-refinement-v1.css' });
  await page.addStyleTag({ url: '/templates/static/css/ui-refinement-final-v1.css' });
  if (withScript) {
    await page.addScriptTag({ url: '/templates/static/js/ui-refinement-v1.js' });
    await expect(page.locator('body')).toHaveClass(/lar-ui-refinement-v1/);
  }
}

async function normalizeFixtureInputs(page) {
  await page.evaluate(() => {
    document.querySelectorAll('input:not([type])').forEach((input) => input.setAttribute('type', 'text'));
  });
}

async function settle(page) {
  await page.mouse.move(0, 0);
  await page.evaluate(() => window.scrollTo({ top: 0, left: 0, behavior: 'instant' }));
  await page.waitForTimeout(300);
}

async function expectNoOverflow(page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
}

test('dashboard uses compact mobile proportions and wider data workspace', async ({ page, viewport }, testInfo) => {
  await page.goto('/tests/ui/fixtures/dashboard.html');
  await loadRefinement(page, false);

  const width = viewport?.width || 0;
  if (width <= 700) {
    const hero = await page.locator('.dash-hero').boundingBox();
    expect(hero.height).toBeLessThanOrEqual(245);
    const columns = await page.locator('.dash-sys-grid').evaluate((node) => getComputedStyle(node).gridTemplateColumns.split(' ').length);
    expect(columns).toBe(2);
    const cards = await page.locator('.dash-storage, .dash-meter').evaluateAll((nodes) => nodes.map((node) => node.getBoundingClientRect().height));
    expect(Math.max(...cards)).toBeLessThanOrEqual(135);
  } else if (width >= 1600) {
    const content = await page.locator('#content').boundingBox();
    expect(content.width).toBeGreaterThan(1240);
  }

  await expectNoOverflow(page);
  await settle(page);
  await page.screenshot({ path: testInfo.outputPath(`refine-dashboard-${testInfo.project.name}.png`), fullPage: true });
});

test('recording prioritizes channel cards and compacts system metrics on mobile', async ({ page, viewport }, testInfo) => {
  await page.route('**/api/update_metadata/*', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ metadata: { live_title: '실제 방송 제목', category: '토크' } }) }));
  await page.goto('/tests/ui/fixtures/recording.html');
  await loadRefinement(page);

  const width = viewport?.width || 0;
  const card = await page.locator('#channel-list > .channel').first().boundingBox();
  if (width <= 700) {
    const channels = await page.locator('#channel-list').boundingBox();
    const system = await page.locator('#sys-dashboard').boundingBox();
    expect(channels.y).toBeLessThan(system.y);
    const columns = await page.locator('#sys-dashboard').evaluate((node) => getComputedStyle(node).gridTemplateColumns.split(' ').length);
    expect(columns).toBe(2);
    await expect(page.locator('.filter-container')).toHaveClass(/lar-mobile-collapsed/);
    const toggle = page.locator('.lar-recording-filter-toggle');
    await expect(toggle).toBeVisible();
    await toggle.click();
    await expect(page.locator('.filter-container')).not.toHaveClass(/lar-mobile-collapsed/);
    await toggle.click();
    await expect(page.locator('.filter-container')).toHaveClass(/lar-mobile-collapsed/);
  } else {
    expect(card.width).toBeLessThanOrEqual(421);
  }

  await expectNoOverflow(page);
  await settle(page);
  await page.screenshot({ path: testInfo.outputPath(`refine-recording-${testInfo.project.name}.png`), fullPage: true });
});

test('settings save bar appears only for unsaved changes and stays compact', async ({ page, viewport }, testInfo) => {
  await page.goto('/tests/ui/fixtures/config.html');
  await expect(page.locator('.lar-config-savebar')).toBeAttached();
  await page.waitForTimeout(500);
  await loadRefinement(page);

  const bar = page.locator('.lar-config-savebar');
  await expect(bar).toBeHidden();
  await page.locator('#autoRecordingMode').selectOption('false');
  await expect(bar).toHaveClass(/is-dirty/);
  await expect(bar).toBeVisible();
  if ((viewport?.width || 0) <= 700) {
    const box = await bar.boundingBox();
    expect(box.height).toBeLessThanOrEqual(78);
    await expect(bar.locator('span')).toBeHidden();
  }

  await expectNoOverflow(page);
  await settle(page);
  await page.screenshot({ path: testInfo.outputPath(`refine-config-${testInfo.project.name}.png`), fullPage: true });
});

test('authentication removes the empty console shell', async ({ page, viewport }, testInfo) => {
  await page.goto('/tests/ui/fixtures/login-audit.html');
  await expect(page.locator('body')).toHaveClass(/lar-auth-mode/);
  await loadRefinement(page, false);

  await expect(page.locator('.navbar-container')).toBeHidden();
  await expect(page.locator('.sidenav')).toBeHidden();
  const card = await page.locator('.lar-auth-card').boundingBox();
  expect(Math.abs(card.x + card.width / 2 - (viewport.width / 2))).toBeLessThanOrEqual(3);

  await expectNoOverflow(page);
  await settle(page);
  await page.screenshot({ path: testInfo.outputPath(`refine-auth-${testInfo.project.name}.png`), fullPage: true });
});

test('channel registration hides advanced fields on small screens', async ({ page, viewport }, testInfo) => {
  await page.goto('/tests/ui/fixtures/channels-audit.html');
  await normalizeFixtureInputs(page);
  await expect(page.locator('#addChannelForm .lar-field')).toHaveCount(8);
  await loadRefinement(page);

  const toggle = page.locator('.lar-channel-advanced-toggle');
  const advanced = page.locator('.lar-channel-advanced-fields');
  if ((viewport?.width || 0) <= 700) {
    await expect(toggle).toBeVisible();
    await expect(advanced).toBeHidden();
    await toggle.click();
    await expect(advanced).toBeVisible();
    await expect(advanced.locator('.lar-field')).toHaveCount(5);
    await toggle.click();
    await expect(advanced).toBeHidden();
  } else {
    await expect(toggle).toBeHidden();
    await expect(advanced).toBeVisible();
  }

  await expectNoOverflow(page);
  await settle(page);
  await page.screenshot({ path: testInfo.outputPath(`refine-channels-${testInfo.project.name}.png`), fullPage: true });
});

test('file actions use clear hierarchy and selection-gated mobile controls', async ({ page, viewport }, testInfo) => {
  await page.goto('/tests/ui/fixtures/files-audit.html');
  await expect(page.locator('.lar-toolbar-actions')).toBeAttached();
  await loadRefinement(page);

  const primary = page.locator('#btnMkdir');
  const secondary = page.locator('#btnUp');
  const danger = page.locator('#mobDelete');
  await expect(primary).toHaveClass(/lar-file-action-primary/);
  await expect(secondary).toHaveClass(/lar-file-action-secondary/);
  await expect(danger).toHaveClass(/lar-file-action-danger/);
  await expect(primary).toHaveCSS('background-color', 'rgb(255, 111, 15)');
  await expect(primary).toHaveCSS('color', 'rgb(255, 255, 255)');
  await expect(secondary).toHaveCSS('background-color', 'rgb(255, 255, 255)');
  await expect(danger).toHaveCSS('color', 'rgb(229, 72, 77)');

  if ((viewport?.width || 0) <= 700) {
    const bar = page.locator('#mobileActionBar');
    await expect(bar).not.toHaveClass(/lar-has-selection/);
    await page.locator('.file-browser tbody input[type="checkbox"]').evaluate((input) => {
      input.checked = true;
      input.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await expect(bar).toHaveClass(/lar-has-selection/);
  }

  await expectNoOverflow(page);
  await settle(page);
  await page.screenshot({ path: testInfo.outputPath(`refine-files-${testInfo.project.name}.png`), fullPage: true });
});

test('cookie and operations cards use intentional desktop and mobile ratios', async ({ page, viewport }, testInfo) => {
  const width = viewport?.width || 0;

  await page.goto('/tests/ui/fixtures/cookies-audit.html');
  await expect(page.locator('.lar-cookie-panel')).toHaveCount(2);
  await loadRefinement(page, false);
  if (width > 900) {
    const first = await page.locator('.lar-cookie-panel').first().boundingBox();
    const second = await page.locator('.lar-cookie-panel').nth(1).boundingBox();
    expect(first.width / second.width).toBeGreaterThan(1.45);
  }
  await expectNoOverflow(page);

  await page.goto('/tests/ui/fixtures/operations.html');
  await page.addStyleTag({ url: '/templates/static/css/operations-controls-v1.css' });
  await loadRefinement(page);
  if (width <= 700) {
    const first = await page.locator('.ops-kpi').first().boundingBox();
    const last = await page.locator('.ops-kpi').last().boundingBox();
    expect(last.width).toBeGreaterThan(first.width * 1.8);
    await expect(page.locator('.ops-tabs')).toHaveClass(/lar-can-scroll/);
  }

  await expectNoOverflow(page);
  await settle(page);
  await page.screenshot({ path: testInfo.outputPath(`refine-operations-${testInfo.project.name}.png`), fullPage: true });
});
