const { test, expect } = require('@playwright/test');

const fixture = '/tests/ui/fixtures/operations-platform-v3.html';

async function stubApi(page) {
  await page.route('**/api/v3/platform/settings', async (route) => {
    if (route.request().method() === 'PUT') {
      const body = JSON.parse(route.request().postData() || '{}');
      return route.fulfill({ json: {
        notifications: body.notifications || { enabled: true, max_attempts: 5, quiet_start: '', quiet_end: '', events: {} },
        archive: body.archive || { enabled: false, remote: '', auto_after_validation: false, delete_after: false, verify_size: true },
        webhooks: body.webhooks || []
      }});
    }
    return route.fulfill({ json: {
      notifications: { enabled: true, max_attempts: 5, quiet_start: '', quiet_end: '', events: { 'recording.completed': true } },
      archive: { enabled: true, remote: 'gdrive:LiveAutoRecorder', auto_after_validation: true, delete_after: false, verify_size: true },
      webhooks: []
    }});
  });
  await page.route('**/api/v3/recordings**', async (route) => route.fulfill({ json: {
    total: 1, limit: 150, offset: 0, items: [{
      id: 7, started_at: '2026-08-07 08:00:00', channel_name: '테스트 채널', platform: 'chzzk',
      title: '테스트 방송', filename: 'sample.mp4', file_path: '/app/chzzk/sample.mp4', duration: '01:00:00',
      status: 'completed', validation_status: 'ok', validation_detail: '영상 + 오디오 · 3600.0초',
      archive_status: '', archive_target: ''
    }]
  }}));
  await page.route('**/api/v3/notifications**', async (route) => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v3/tokens', async (route) => {
    if (route.request().method() === 'POST') {
      return route.fulfill({ json: { id: 3, name: 'Home Assistant', token: 'lar_once_only_token', prefix: 'lar_once_onl', scopes: ['read'], expires_epoch: 0 } });
    }
    return route.fulfill({ json: { items: [] } });
  });
  await page.route('**/api/v3/recordings/7/verify', async (route) => route.fulfill({ json: { status: 'ok', detail: 'verified' } }));
  await page.route('**/api/v3/recordings/7/archive', async (route) => route.fulfill({ json: { status: 'queued' } }));
}

test('operations adds history notifications archive and automation tabs', async ({ page }) => {
  await stubApi(page);
  await page.goto(fixture);

  await expect(page.getByRole('tab', { name: '녹화 기록' })).toBeVisible();
  await expect(page.getByRole('tab', { name: '알림 센터' })).toBeVisible();
  await expect(page.getByRole('tab', { name: '외부 보관' })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'API·웹훅' })).toBeVisible();
});

test('history renders durable record and exposes verify and archive actions', async ({ page }) => {
  await stubApi(page);
  await page.goto(fixture);
  await page.getByRole('tab', { name: '녹화 기록' }).click();

  await expect(page.locator('#ops-history-body')).toContainText('테스트 채널');
  await expect(page.locator('#ops-history-body')).toContainText('테스트 방송');
  await expect(page.locator('#ops-history-body')).toContainText('정상');
  await page.getByRole('button', { name: '검증·복구' }).click();
  await expect(page.locator('#ops-notice')).toContainText('검증');
  await page.getByRole('button', { name: '외부 보관' }).click();
  await expect(page.locator('#ops-notice')).toContainText('대기열');
});

test('api token is displayed once after creation', async ({ page }) => {
  await stubApi(page);
  await page.goto(fixture);
  await page.getByRole('tab', { name: 'API·웹훅' }).click();

  await page.locator('#ops-token-form input[name="name"]').fill('Home Assistant');
  await page.getByRole('button', { name: '토큰 생성' }).click();
  await expect(page.locator('#ops-token-once')).toContainText('다시 표시되지 않습니다');
  await expect(page.locator('#ops-token-once code')).toHaveText('lar_once_only_token');
});

test('operations platform has no page-level horizontal overflow', async ({ page }) => {
  await stubApi(page);
  await page.goto(fixture);
  await page.getByRole('tab', { name: '녹화 기록' }).click();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
