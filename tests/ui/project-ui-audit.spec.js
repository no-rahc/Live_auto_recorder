const { test, expect } = require('@playwright/test');

async function loadAuditFixes(page) {
  await page.addStyleTag({ url: '/templates/static/css/project-ui-audit-fixes-v1.css' });
}

async function normalizeFixtureInputs(page) {
  await page.evaluate(() => {
    document.querySelectorAll('input:not([type])').forEach((input) => input.setAttribute('type', 'text'));
  });
}

async function resetScreenshotViewport(page) {
  await page.mouse.move(0, 0);
  await page.evaluate(() => window.scrollTo({ top: 0, left: 0, behavior: 'instant' }));
}

async function expectNoHorizontalOverflow(page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
}

test('channel management keeps summaries compact and opens editing on demand', async ({ page, viewport }, testInfo) => {
  await page.goto('/tests/ui/fixtures/channels-audit.html');
  await loadAuditFixes(page);
  await normalizeFixtureInputs(page);
  await expect(page.locator('body')).toHaveClass(/lar-project-ui-audit/);
  await expect(page.locator('#addChannelForm .lar-field')).toHaveCount(8);

  const cards = page.locator('.channel-card');
  await expect(cards).toHaveCount(2);
  await expect(cards.first().locator('.channel-edit-form')).toBeHidden();
  const toggle = cards.first().locator('.lar-channel-edit-toggle');
  await expect(toggle).toHaveText('설정 열기');
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await toggle.hover();
  const hoverStyle = await toggle.evaluate((node) => ({
    background: getComputedStyle(node).backgroundColor,
    color: getComputedStyle(node).color,
  }));
  expect(hoverStyle.background).toBe('rgb(255, 242, 232)');
  expect(hoverStyle.color).toBe('rgb(232, 95, 0)');

  await toggle.click();
  await expect(cards.first().locator('.channel-edit-form')).toBeVisible();
  await expect(toggle).toHaveText('설정 닫기');
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  await toggle.click();
  await expect(toggle).toHaveText('설정 열기');
  await expect(cards.first().locator('.channel-edit-form')).toBeHidden();

  if ((viewport?.width || 0) >= 901) {
    const fields = await page.locator('#addChannelForm .lar-field').allInnerTexts();
    expect(fields.some((value) => value.includes('저장 경로'))).toBeTruthy();
  }
  await expectNoHorizontalOverflow(page);
  await resetScreenshotViewport(page);
  await page.screenshot({ path: testInfo.outputPath(`project-channels-${testInfo.project.name}.png`), fullPage: true });
});

test('cookie management groups providers and masks sensitive values', async ({ page, viewport }, testInfo) => {
  await page.goto('/tests/ui/fixtures/cookies-audit.html');
  await loadAuditFixes(page);
  const panels = page.locator('.lar-cookie-panel');
  await expect(panels).toHaveCount(2);
  const secret = page.locator('#NID_AUT');
  await expect(secret).toHaveAttribute('type', 'password');
  const toggle = secret.locator('xpath=..').locator('.lar-password-toggle');
  await expect(toggle).toHaveAccessibleName('비밀번호 표시');
  await toggle.hover();
  await expect(toggle).toHaveCSS('background-color', 'rgb(255, 242, 232)');
  await toggle.click();
  await expect(secret).toHaveAttribute('type', 'text');
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  await expect(toggle).toHaveAccessibleName('비밀번호 숨기기');

  const first = await panels.first().boundingBox();
  const second = await panels.nth(1).boundingBox();
  if ((viewport?.width || 0) > 900) expect(second.x).toBeGreaterThan(first.x + 20);
  else expect(second.y).toBeGreaterThan(first.y);

  await expectNoHorizontalOverflow(page);
  await resetScreenshotViewport(page);
  await page.screenshot({ path: testInfo.outputPath(`project-cookies-${testInfo.project.name}.png`), fullPage: true });
});

test('file manager toolbar, mobile actions, and modal keyboard flow stay usable', async ({ page, viewport }, testInfo) => {
  await page.goto('/tests/ui/fixtures/files-audit.html');
  await loadAuditFixes(page);
  await expect(page.locator('.lar-toolbar-field')).toHaveCount(3);
  await expect(page.locator('.lar-toolbar-actions button')).toHaveCount(4);
  await expect(page.locator('#file-detail-modal')).toHaveAttribute('role', 'dialog');
  await expect(page.locator('#file-detail-modal')).toHaveAttribute('aria-modal', 'true');

  await page.locator('#file-detail-modal').evaluate((node) => node.classList.remove('hidden'));
  await expect(page.locator('#file-detail-modal')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('#file-detail-modal')).toBeHidden();

  if ((viewport?.width || 0) <= 620) {
    const bar = await page.locator('#mobileActionBar').boundingBox();
    expect(bar.x).toBeGreaterThanOrEqual(0);
    expect(bar.x + bar.width).toBeLessThanOrEqual(viewport.width);
  }

  await expectNoHorizontalOverflow(page);
  await resetScreenshotViewport(page);
  await page.screenshot({ path: testInfo.outputPath(`project-files-${testInfo.project.name}.png`), fullPage: true });
});

test('login uses one centered card and supports password reveal', async ({ page, viewport }, testInfo) => {
  await page.goto('/tests/ui/fixtures/login-audit.html');
  await loadAuditFixes(page);
  await normalizeFixtureInputs(page);
  await expect(page.locator('body')).toHaveClass(/lar-auth-mode/);
  const outer = page.locator('#content > .login-form');
  await expect(outer).toHaveClass(/lar-auth-card/);
  const borders = await page.evaluate(() => ({
    outer: getComputedStyle(document.querySelector('#content > .login-form')).borderTopWidth,
    inner: getComputedStyle(document.querySelector('#loginForm')).borderTopWidth,
  }));
  expect(borders.outer).not.toBe('0px');
  expect(borders.inner).toBe('0px');

  if ((viewport?.width || 0) >= 1100) {
    const content = await page.locator('#content').boundingBox();
    const expectedCenter = (244 + viewport.width) / 2;
    expect(Math.abs(content.x + content.width / 2 - expectedCenter)).toBeLessThanOrEqual(2);
  }

  const password = page.locator('#password');
  const reveal = page.getByRole('button', { name: '비밀번호 표시' });
  await reveal.hover();
  await expect(reveal).toHaveCSS('background-color', 'rgb(255, 242, 232)');
  await reveal.click();
  await expect(password).toHaveAttribute('type', 'text');
  await expectNoHorizontalOverflow(page);
  await resetScreenshotViewport(page);
  await page.screenshot({ path: testInfo.outputPath(`project-login-${testInfo.project.name}.png`), fullPage: true });
});

test('registration is centered and reports password match without changing form behavior', async ({ page, viewport }, testInfo) => {
  await page.goto('/tests/ui/fixtures/register-audit.html');
  await loadAuditFixes(page);
  await normalizeFixtureInputs(page);
  await expect(page.locator('body')).toHaveClass(/lar-auth-mode/);

  if ((viewport?.width || 0) >= 1100) {
    const content = await page.locator('#content').boundingBox();
    const expectedCenter = (244 + viewport.width) / 2;
    expect(Math.abs(content.x + content.width / 2 - expectedCenter)).toBeLessThanOrEqual(2);
  }

  await page.locator('#password').fill('password-one');
  await page.locator('#password_confirm').fill('password-two');
  await expect(page.locator('.lar-password-match')).toHaveText('비밀번호가 일치하지 않습니다.');
  await expect(page.locator('.lar-password-match')).toHaveAttribute('data-state', 'error');
  await page.locator('#password_confirm').fill('password-one');
  await expect(page.locator('.lar-password-match')).toHaveText('비밀번호가 일치합니다.');
  await expect(page.locator('.lar-password-match')).toHaveAttribute('data-state', 'ok');
  await expectNoHorizontalOverflow(page);
  await resetScreenshotViewport(page);
  await page.screenshot({ path: testInfo.outputPath(`project-register-${testInfo.project.name}.png`), fullPage: true });
});
