import { expect, test } from '@playwright/test';

const durable = process.env.UI_DURABLE_JOBS === 'true';

test('real app preserves original routes, integrated assets, redirects and local-only API boundaries',async({page,request})=>{
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'녹화 관제 보드'})).toBeVisible();
  await expect(page.locator('#root')).toHaveCount(0);
  await expect(page.locator('script[src*="/static/js/console.js"]')).toHaveCount(1);
  await expect(page.locator('script[src*="/static/library/"]')).toHaveCount(0);
  for(const path of ['/channels','/config','/recording','/operations','/files']) {
    const response=await request.get(path);expect(response.status(),path).toBe(200);
    const html=await response.text();expect(html).not.toContain('id="root"');expect(html).toContain('/static/css/console.css');
  }
  for(const [from,to] of [['/v2','/'],['/v2/channels','/channels'],['/v2/settings','/config'],['/v2/broadcasts','/broadcasts'],['/v2/jobs','/jobs'],['/v2/broadcasts/browser-test-broadcast','/broadcasts/browser-test-broadcast']]) {
    const response=await request.get(from+'?preview=1',{maxRedirects:0});
    expect([302,307,308]).toContain(response.status());expect(response.headers().location).toBe(to+'?preview=1');
  }
  for(const asset of ['/static/library/library.js','/static/library/library.css']) {
    const response=await request.get(asset);expect(response.status(),asset).toBe(200);expect((await response.body()).length).toBeGreaterThan(100);
  }
  expect((await request.get('/api/v3/automation/status')).status()).toBe(401);
});

test('real catalog appears inside v1 shell and durable-disabled mode cannot create jobs',async({page,request})=>{
  const response=await request.get('/api/v2/broadcasts?limit=50');expect(response.status()).toBe(200);
  const list=await response.json();expect(list.items).toHaveLength(1);expect(list.items[0].id).toBe('browser-test-broadcast');
  await page.goto('/broadcasts');await expect(page.locator('#root.library-workspace')).toBeVisible();
  await page.getByRole('link',{name:'상세 보기'}).click();
  await expect(page.locator('#root h1')).toHaveText('안전한 로컬 테스트 방송');
  await expect(page.locator('.artifact-list').first()).toContainText('sample-1.ts');
  await expect(page.locator('.artifact-list').first()).toContainText('sample-2.ts');
  if(!durable) {
    await expect(page.getByRole('button',{name:'조각 합치기'})).toBeDisabled();
    await expect(page.getByText('파일 작업 기능이 꺼져 있습니다.')).toBeVisible();
    const blocked=await request.post('/api/v2/jobs',{headers:{'Idempotency-Key':'disabled-browser-test'},data:{kind:'verify',target_id:'1',input_revision:1,options:{}}});
    expect(blocked.status()).toBe(409);
    await page.goto('/jobs?selected=anything');await expect(page.getByText('파일 작업 기능이 꺼져 있습니다',{exact:true})).toBeVisible();await expect(page.getByRole('dialog')).toHaveCount(0);
  } else {
    await expect(page.getByRole('button',{name:'조각 합치기'})).toBeEnabled();
    await page.getByRole('button',{name:'조각 합치기'}).click();await expect(page.getByRole('dialog')).toBeVisible();
    await page.getByRole('button',{name:'돌아가기',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);
    const jobs=await (await request.get('/api/v2/jobs')).json();expect(jobs.items).toHaveLength(0);
    await page.goto('/jobs');await expect(page.locator('#root h1')).toHaveText('작업 상태');
    await expect(page.getByText('조건에 맞는 작업이 없습니다')).toBeVisible();
  }
  await page.goto('/');await expect(page.getByRole('heading',{name:'녹화 관제 보드'})).toBeVisible();
});
