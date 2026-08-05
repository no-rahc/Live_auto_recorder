const { test, expect } = require('@playwright/test');

const fixture = '/tests/ui/fixtures/config.html';

test('settings workspace reduces the page to five focused groups', async ({ page, viewport }, testInfo) => {
  await page.route('**/api/config-tools/path-check', async (route) => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ status: 'ok', writable: true, free_gb: 812.4, message: '경로가 존재하며 쓰기 권한이 있습니다.' }) });
  });
  await page.route('**/api/config-tools/encoders', async (route) => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ status: 'ok', encoders: [{ id: 'libx264', label: 'H.264 CPU', available: true }, { id: 'h264_nvenc', label: 'H.264 NVIDIA NVENC', available: false }] }) });
  });

  await page.goto(fixture);
  const tabs = page.locator('.lar-config-tab');
  await expect(tabs).toHaveCount(5);
  await expect(page.getByRole('button', { name: /기본 녹화/ })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByText('녹화 기본 설정')).toBeVisible();
  await expect(page.getByText('설정 백업 / 복원')).toHaveCount(0);
  await expect(page.getByText('녹화 파일 정리')).toHaveCount(0);
  await expect(page.locator('#enableTray').locator('xpath=ancestor::div[contains(@class,"lar-setting-row")]')).toBeHidden();

  const filename = page.locator('#filenamePattern');
  await filename.fill('{channel_name}_{recording_time}{file_extension}');
  await expect(page.locator('.lar-filename-preview code')).toContainText('샘플채널_260805_155400.ts');

  await page.getByRole('button', { name: /치지직/ }).click();
  await expect(page.getByText('치지직 플러그인')).toBeVisible();
  await expect(page.locator('#timemachine_time_shift').locator('xpath=ancestor::div[contains(@class,"lar-setting-row")]')).toBeHidden();
  await page.locator('#plugin_type').selectOption('timemachine_plus');
  await expect(page.locator('#timemachine_time_shift').locator('xpath=ancestor::div[contains(@class,"lar-setting-row")]')).toBeVisible();
  await expect(page.locator('#autoStopInterval').locator('xpath=ancestor::div[contains(@class,"lar-setting-row")]')).toBeHidden();
  await page.locator('#splitRecordingMode').selectOption('true');
  await expect(page.locator('#autoStopInterval').locator('xpath=ancestor::div[contains(@class,"lar-setting-row")]')).toBeVisible();

  await page.getByRole('button', { name: /후처리·인코딩/ }).click();
  await expect(page.locator('#larEncodingProfile')).toBeVisible();
  await expect(page.locator('#video_codec').locator('xpath=ancestor::div[contains(@class,"lar-setting-row")]')).toBeHidden();
  await page.locator('#larEncodingProfile').selectOption('balanced');
  await expect(page.locator('#stream_copy')).toHaveValue('false');
  await expect(page.locator('#video_codec').locator('xpath=ancestor::div[contains(@class,"lar-setting-row")]')).toBeVisible();
  await page.getByRole('button', { name: '이 서버의 인코더 확인' }).click();
  await expect(page.locator('.lar-encoder-result')).toContainText('H.264 CPU');
  await page.getByRole('button', { name: '경로 확인' }).click();
  await expect(page.locator('.lar-field-result')).toContainText('여유 812.4 GB');

  await page.getByRole('button', { name: /^알림/ }).click();
  await expect(page.locator('.lar-notification-tabs')).toBeVisible();
  await page.getByRole('button', { name: 'Discord', exact: true }).click();
  await expect(page.locator('[data-config-panel="notifications"] .config-section:visible h3')).toHaveText('Discord');

  await page.getByRole('button', { name: /시스템·보안/ }).click();
  await expect(page.getByRole('link', { name: '운영 관리 열기' })).toBeVisible();
  await expect(page.getByText('계정 정보 관리')).toBeVisible();

  const saveBar = page.locator('.lar-config-savebar');
  await expect(saveBar).toBeVisible();
  await page.locator('#loginMode').selectOption('false');
  await expect(saveBar).toHaveClass(/is-dirty/);
  await expect(page.getByRole('button', { name: '설정 저장' })).toBeEnabled();

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);

  if ((viewport?.width || 0) >= 1100) {
    const visibleSections = page.locator('.lar-config-panel.is-active .config-section:visible');
    expect(await visibleSections.count()).toBeGreaterThan(0);
  }

  await page.screenshot({ path: testInfo.outputPath(`config-workspace-${testInfo.project.name}.png`), fullPage: true });
});
