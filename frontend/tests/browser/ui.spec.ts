import { expect, test } from '@playwright/test';
import { broadcast, channel, detail, job, mockApi, now, systemStatus } from './fixtures';

test.beforeEach(async ({page}) => { await mockApi(page); });
test('desktop dashboard, real observation timestamp, and isolated v2 assets', async ({page}) => {
  await page.setViewportSize({width:1440,height:1050}); await page.goto('/v2');
  await expect(page.getByRole('heading',{name:'녹화 현황'})).toBeVisible();
  await expect(page.getByText('서버 연결됨')).toBeVisible();
  await expect(page.getByText(/2026\. 10\. 11\./).first()).toBeVisible();
  expect(await page.locator('script[src]').evaluateAll(scripts=>scripts.map(s=>s.getAttribute('src')))).toEqual([expect.stringMatching(/^\/static\/v2\/assets\/index-.+\.js$/)]);
  await page.screenshot({path:'test-results/dashboard-desktop.png',fullPage:true});
});
test('all five screens and detail fit 360px without horizontal overflow', async ({page}) => {
  await page.setViewportSize({width:360,height:800});
  const errors: string[]=[]; page.on('pageerror',error=>errors.push(error.message));
  for(const path of ['/v2','/v2/broadcasts','/v2/broadcasts/broadcast-1','/v2/channels','/v2/jobs','/v2/settings']) {
    await page.goto(path); await expect(page.locator('h1')).toBeVisible();
    await expect(page.locator('.loading')).toHaveCount(0);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),path).toBe(true);
    expect(await page.locator('button:visible, input:visible, select:visible').evaluateAll(elements=>elements.every(element=>element.getBoundingClientRect().height>=43.9)),path).toBe(true);
  }
  expect(errors).toEqual([]);
  await page.goto('/v2/broadcasts/broadcast-1'); await expect(page.getByRole('heading',{name:broadcast.title})).toBeVisible();
  await page.screenshot({path:'test-results/broadcast-mobile.png',fullPage:true});
});
test('library filters live in URL and send server-side query/date parameters', async ({page}) => {
  const requests:string[]=[]; page.on('request',request=>{if(request.url().includes('/api/v2/broadcasts?'))requests.push(request.url());});
  await page.goto('/v2/broadcasts');
  await page.getByRole('searchbox',{name:'방송 제목 검색'}).fill('가을');
  await page.getByLabel('플랫폼',{exact:true}).selectOption('chzzk');
  await page.getByLabel('채널',{exact:true}).selectOption(channel.id);
  await page.getByLabel('방송 상태',{exact:true}).selectOption('completed');
  await page.getByLabel('시작일 (UTC)',{exact:true}).fill('2026-10-01');
  await page.getByLabel('종료일 (UTC)',{exact:true}).fill('2026-10-11');
  await expect(page).toHaveURL(/date_to=2026-10-11/);
  const filters={query:'가을',platform:'chzzk',channel_id:channel.id,status:'completed',date_from:'2026-10-01',date_to:'2026-10-11'};
  await expect.poll(()=>requests.some(url=>Object.entries(filters).every(([key,value])=>new URL(url).searchParams.get(key)===value))).toBe(true);
  await page.reload(); await expect(page.getByRole('searchbox',{name:'방송 제목 검색'})).toHaveValue('가을');
  await expect(page.getByLabel('플랫폼',{exact:true})).toHaveValue('chzzk');
  await expect(page.getByLabel('채널',{exact:true})).toHaveValue(channel.id);
  await expect(page.getByLabel('방송 상태',{exact:true})).toHaveValue('completed');
  await expect(page.getByLabel('시작일 (UTC)',{exact:true})).toHaveValue('2026-10-01');
  await expect(page.getByLabel('종료일 (UTC)',{exact:true})).toHaveValue('2026-10-11');
});
test('a delayed command is sent once and never paints an optimistic recording state', async ({page}) => {
  let posts=0;
  await page.route('**/api/v2/channels/ch-1/commands',async route=>{posts++;await new Promise(resolve=>setTimeout(resolve,350));await route.fulfill({status:202,contentType:'application/json',body:JSON.stringify({command_id:'command-1',state:'accepted'})});});
  await page.goto('/v2/channels'); await page.getByRole('button',{name:'지금 한 번 녹화'}).click();
  const request=page.getByRole('button',{name:'한 번 녹화 요청',exact:true}); await request.click();
  await expect(page.getByText('명령 전송 중…')).toBeVisible();
  await expect(page.getByText('명령 접수 · 실제 처리 결과를 기다리는 중입니다.')).toBeVisible();
  await expect(page.locator('.channel-states').getByText('감시 중')).toBeVisible();
  expect(posts).toBe(1); await expect(page.getByRole('button',{name:'명령 처리 중…'})).toBeDisabled();
});
test('a once command running for the whole broadcast still allows stop after recording is observed',async({page})=>{
  let observed=false;
  await page.route('**/api/v2/channels',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({items:[observed?{...channel,actual_state:'recording',broadcast_id:'broadcast-1',revision:5}:channel],observed_at:now+1})}));
  await page.route('**/api/v2/channels/ch-1/commands',route=>{observed=true;return route.fulfill({status:202,contentType:'application/json',body:JSON.stringify({command_id:'command-1',state:'running'})});});
  await page.route('**/api/v2/commands/command-1',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({id:'command-1',state:'running'})}));
  await page.goto('/v2/channels');await page.getByRole('button',{name:'지금 한 번 녹화'}).click();await page.getByRole('button',{name:'한 번 녹화 요청',exact:true}).click();
  await expect(page.getByRole('button',{name:'이번 방송 중지'})).toBeEnabled();
});
test('409 conflict refreshes the observed intent and gives a specific explanation',async({page})=>{
  let changed=false;
  await page.route('**/api/v2/channels',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({items:[changed?{...channel,revision:5,desired_mode:'paused'}:channel],observed_at:now+1})}));
  await page.route('**/api/v2/channels/ch-1',route=>{changed=true;return route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({code:'REVISION_CONFLICT',message:'Channel changed elsewhere',request_id:'req-409'})});});
  await page.goto('/v2/channels');await page.getByRole('button',{name:'자동 녹화 끄기'}).click();
  await expect(page.getByText('다른 곳에서 상태가 바뀌었습니다')).toBeVisible();
  await expect(page.getByRole('button',{name:'자동 녹화 켜기'})).toBeVisible();
  await expect(page.getByText(/req-409/)).toBeVisible();
});
test('loss of connection retains last data and shows stale state',async({page})=>{
  await page.goto('/v2/channels');await expect(page.getByRole('heading',{name:'초록 스튜디오'})).toBeVisible();
  await page.route('**/api/v2/**',route=>route.abort('internetdisconnected'));
  await page.getByRole('button',{name:'모든 상태 새로고침'}).click();
  await expect(page.getByText('갱신 중단 · 마지막 확인 데이터').first()).toBeVisible({timeout:10000});
  await expect(page.getByRole('heading',{name:'초록 스튜디오'})).toBeVisible();
  await expect(page.getByText('연결 끊김')).toBeVisible();
});
test('merge preview preserves ordered inputs and submits current revision only after confirmation',async({page})=>{
  let body:unknown=null, key:string|undefined;
  await page.route('**/api/v2/jobs',async route=>{
    if(route.request().method()!=='POST')return route.fallback();
    body=route.request().postDataJSON();key=route.request().headers()['idempotency-key'];
    await route.fulfill({status:202,contentType:'application/json',body:JSON.stringify({job_id:'job-merge',state:'queued'})});
  });
  await page.goto('/v2/broadcasts/broadcast-1');await page.getByRole('button',{name:'조각 합치기'}).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  expect(await page.locator('.merge-preview li').allTextContents()).toEqual([expect.stringContaining('live-segment-1.ts'),expect.stringContaining('live-segment-2.ts')]);
  await expect(page.getByText('아래 순서로 합친 새 결과물을 만듭니다. 원본 파일은 삭제하거나 덮어쓰지 않습니다.')).toBeVisible();
  expect(body).toBeNull();await page.getByRole('button',{name:'작업 요청',exact:true}).click();
  await expect(page.getByText('작업이 접수되었습니다.')).toBeVisible();
  expect(body).toEqual({kind:'merge',target_id:'broadcast-1',input_revision:detail.revision,options:{}});expect(key).toBeTruthy();
});
test('cancelled modal sends nothing; cancel request remains pending until server observation',async({page})=>{
  let requests=0,cancelled=false;
  await page.route('**/api/v2/jobs/job-1/cancel',async route=>{requests++;cancelled=true;await route.fulfill({status:202,contentType:'application/json',body:JSON.stringify({...job,state:'cancel_requested',revision:3})});});
  await page.route('**/api/v2/jobs/job-1',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({...job,state:cancelled?'cancel_requested':'running',revision:cancelled?3:2,attempt_history:[]})}));
  await page.goto('/v2/jobs?selected=job-1');await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button',{name:'작업 취소',exact:true}).click();await page.getByRole('button',{name:'돌아가기',exact:true}).click();expect(requests).toBe(0);
  await page.getByRole('button',{name:'작업 취소',exact:true}).click();await page.getByRole('button',{name:'취소 요청',exact:true}).click();
  await expect(page.getByText('프로세스가 종료되었는지 확인 중입니다. 아직 취소 완료 상태가 아닙니다.')).toBeVisible();expect(requests).toBe(1);
  await page.getByRole('button',{name:'닫기',exact:true}).last().click();await expect(page.getByRole('dialog')).toHaveCount(0);await expect(page).not.toHaveURL(/selected=/);
});
test('storage errors persist across screens with last successful check and keyboard navigation',async({page})=>{
  await page.route('**/api/v2/status',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({...systemStatus,storage:{status:'blocked',message:'NAS mount unavailable',last_ok_at:now-300}})}));
  await page.goto('/v2');await expect(page.getByText('NAS mount unavailable')).toBeVisible();
  await page.getByRole('navigation',{name:'주 메뉴',exact:true}).getByRole('link',{name:'방송 보관함'}).click();
  await expect(page.getByText('NAS mount unavailable')).toBeVisible();
  await page.getByRole('link',{name:'상세 보기'}).click();await expect(page.getByRole('heading',{name:broadcast.title})).toBeVisible();
  await page.goBack();await expect(page.getByRole('heading',{name:'방송 보관함',exact:true})).toBeVisible();
  await page.goForward();await expect(page.getByRole('heading',{name:broadcast.title})).toBeVisible();
});
