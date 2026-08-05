const { test, expect } = require('@playwright/test');

test('dashboard channel row opens editable detail modal', async ({ page }, testInfo) => {
  const channels = [
    {
      id: 'channel-a',
      platform: 'chzzk',
      name: '채널 A',
      output_dir: '/app/chzzk/channel-a',
      quality: 'best',
      extension: '.ts',
      recordWatchParty: false,
      watchPartyExcludeTags: [],
      record_enabled: true,
      live_title: '테스트 방송',
    },
    {
      id: 'channel-b',
      platform: 'youtube',
      name: '채널 B',
      output_dir: '/app/chzzk/channel-b',
      quality: '1080p',
      extension: '.mp4',
      recordWatchParty: false,
      watchPartyExcludeTags: [],
      record_enabled: true,
    },
  ];
  const statuses = {
    'channel-a': { recording: true, duration: '01:24:18', title: '테스트 방송' },
    'channel-b': { recording: false, reserved: false },
  };
  let savedPayload = null;

  await page.route('**/api/channels', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(channels) });
  });
  await page.route('**/status', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(statuses) });
  });
  await page.route('**/api/channels/channel-a', async (route) => {
    savedPayload = route.request().postDataJSON();
    Object.assign(channels[0], savedPayload);
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'success' }) });
  });

  await page.goto('/tests/ui/fixtures/dashboard.html');
  const firstRow = page.locator('#ch-list .ch-row').first();
  await expect(firstRow).toHaveClass(/lar-channel-clickable/);
  await expect(firstRow).toHaveAttribute('role', 'button');
  await firstRow.click();

  const dialog = page.getByRole('dialog', { name: '채널 A' });
  await expect(dialog).toBeVisible();
  await expect(page.locator('#lar-channel-dialog-status')).toHaveText('녹화 중');
  await expect(page.locator('#lar-channel-duration')).toHaveText('01:24:18');
  await expect(page.locator('#lar-channel-recording-note')).toBeVisible();

  const nameInput = page.locator('#lar-channel-detail-form [name="name"]');
  const platformSelect = page.locator('#lar-channel-detail-form [name="platform"]');
  await expect(nameInput).toBeDisabled();
  await expect(platformSelect).toBeDisabled();

  await page.getByRole('button', { name: '수정', exact: true }).click();
  await expect(nameInput).toBeEnabled();
  await expect(platformSelect).toBeDisabled();
  await nameInput.fill('채널 A 수정');
  await page.locator('#lar-channel-detail-form [name="quality"]').selectOption('1080p');
  await page.getByRole('button', { name: '변경사항 저장' }).click();

  await expect.poll(() => savedPayload && savedPayload.name).toBe('채널 A 수정');
  expect(savedPayload.platform).toBe('chzzk');
  expect(savedPayload.output_dir).toBe('/app/chzzk/channel-a');
  expect(savedPayload.quality).toBe('1080p');
  await expect(page.locator('#lar-channel-modal-message')).toHaveText('채널 설정을 저장했습니다.');
  await expect(nameInput).toBeDisabled();

  const box = await dialog.boundingBox();
  const viewport = page.viewportSize();
  expect(box.width).toBeLessThanOrEqual(viewport.width);
  expect(box.height).toBeLessThanOrEqual(viewport.height);

  await page.screenshot({
    path: testInfo.outputPath(`dashboard-channel-modal-${testInfo.project.name}.png`),
    fullPage: true,
  });
});

test('channel modal supports keyboard open and escape close', async ({ page }) => {
  await page.route('**/api/channels', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify([{ id: 'channel-a', platform: 'chzzk', name: '채널 A', output_dir: '/app/chzzk/a', quality: 'best', extension: '.ts' }]),
  }));
  await page.route('**/status', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ 'channel-a': { recording: false } }),
  }));

  await page.goto('/tests/ui/fixtures/dashboard.html');
  const firstRow = page.locator('#ch-list .ch-row').first();
  await firstRow.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toBeHidden();
});
