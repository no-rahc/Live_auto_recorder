import { expect, test } from '@playwright/test';
import { broadcast, channel, detail, job, mockConsoleApi, now } from './fixtures';

test.beforeEach(async ({page}) => { await mockConsoleApi(page); });

test('dashboard stays the original v1 page; library assets load only inside the actual console',async({page})=>{
  await page.setViewportSize({width:1440,height:1050});
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'녹화 관제 보드'})).toBeVisible();
  await expect(page.locator('#root')).toHaveCount(0);
  await expect(page.locator('script[src*="/static/library/"]')).toHaveCount(0);
  await expect(page.locator('script[src*="/static/js/app.js"]')).toHaveCount(1);
  await expect(page.locator('script[src*="/static/js/console.js"]')).toHaveCount(1);
  await page.locator('#mySidenav a[href="/broadcasts"]').click();
  await expect(page).toHaveURL(/\/broadcasts$/);
  await expect(page.locator('#root.library-workspace')).toBeVisible();
  await expect(page.locator('#root').getByRole('heading',{name:'방송 보관함',exact:true})).toBeVisible();
  await expect(page.locator('.navbar')).toHaveCount(1);
  await expect(page.locator('#mySidenav')).toHaveCount(1);
  await expect(page.locator('#root .sidebar, #root .mobile-nav, #root .app-layout')).toHaveCount(0);
  const scripts=await page.locator('script[src]').evaluateAll(nodes=>nodes.map(node=>new URL((node as HTMLScriptElement).src).pathname));
  expect(scripts).toContain('/static/library/library.js');
  expect(scripts).toContain('/static/js/console.js');
  expect(scripts.some(path=>path.includes('/static/v2/'))).toBe(false);
  await expect(page.locator('link[href*="/static/library/library.css"]')).toHaveCount(1);
  await page.locator('#mySidenav a[href="/channels"]').click();
  await expect(page.locator('body')).toHaveClass(/page-channels/);
  await expect(page.locator('#root')).toHaveCount(0);
  await page.locator('#mySidenav a[href="/"]').first().click();
  await expect(page.getByRole('heading',{name:'녹화 관제 보드'})).toBeVisible();
});

test('integrated screens and detail fit 360px with usable controls and no JS errors',async({page})=>{
  await page.setViewportSize({width:360,height:800});
  const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
  for(const path of ['/broadcasts','/broadcasts/broadcast-1','/jobs','/jobs?selected=job-1']) {
    await page.goto(path);await expect(page.locator('#root h1')).toBeVisible();
    await expect(page.locator('#root .loading')).toHaveCount(0);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),path).toBe(true);
    const undersized=await page.locator('#root button:visible, #root input:visible, #root select:visible').evaluateAll(elements=>elements.filter(element=>element.getBoundingClientRect().height<43.9).map(element=>({tag:element.tagName,label:element.getAttribute('aria-label')||element.textContent?.trim(),className:element.className,height:element.getBoundingClientRect().height})));
    expect(undersized,`${path}: controls smaller than the 44px mobile target`).toEqual([]);
    if(path.includes('selected=')) {
      const rect=await page.getByRole('dialog').boundingBox();
      expect(rect).toBeTruthy();expect(rect!.x).toBeGreaterThanOrEqual(0);expect(rect!.x+rect!.width).toBeLessThanOrEqual(360);
    }
  }
  expect(errors).toEqual([]);
});

test('mobile uses the original console menu for library and jobs',async({page})=>{
  await page.setViewportSize({width:360,height:800});await page.goto('/');
  await page.getByRole('button',{name:'메뉴 열기'}).click();
  await page.locator('#mySidenav a[href="/broadcasts"]').click();
  await expect(page.locator('#root h1')).toHaveText('방송 보관함');
  await page.getByRole('button',{name:'메뉴 열기'}).click();
  await page.locator('#mySidenav a[href="/jobs"]').click();
  await expect(page.locator('#root h1')).toHaveText('작업 상태');
});

test('library filters persist in URL, reload, and server-side query/date parameters',async({page})=>{
  const requests:string[]=[];page.on('request',request=>{if(request.url().includes('/api/v2/broadcasts?'))requests.push(request.url());});
  await page.goto('/broadcasts');
  await page.getByRole('searchbox',{name:'방송 제목 검색'}).fill('가을');
  await page.getByLabel('플랫폼',{exact:true}).selectOption('chzzk');
  await page.getByLabel('채널',{exact:true}).selectOption(channel.id);
  await page.getByLabel('방송 상태',{exact:true}).selectOption('completed');
  await page.getByLabel('시작일 (UTC)',{exact:true}).fill('2026-10-01');
  await page.getByLabel('종료일 (UTC)',{exact:true}).fill('2026-10-11');
  const filters={query:'가을',platform:'chzzk',channel_id:channel.id,status:'completed',date_from:'2026-10-01',date_to:'2026-10-11'};
  await expect.poll(()=>requests.some(url=>Object.entries(filters).every(([key,value])=>new URL(url).searchParams.get(key)===value))).toBe(true);
  await page.reload();await expect(page.getByRole('searchbox',{name:'방송 제목 검색'})).toHaveValue('가을');
  for(const [label,value] of [['플랫폼','chzzk'],['채널',channel.id],['방송 상태','completed'],['시작일 (UTC)','2026-10-01'],['종료일 (UTC)','2026-10-11']]) await expect(page.getByLabel(label,{exact:true})).toHaveValue(value);
  await page.getByRole('link',{name:'상세 보기'}).click();await expect(page.locator('#root h1')).toHaveText(broadcast.title);
  await page.goBack();await expect(page.getByRole('searchbox',{name:'방송 제목 검색'})).toHaveValue('가을');
  await page.goForward();await expect(page.locator('#root h1')).toHaveText(broadcast.title);
});

test('merge preview preserves ordered sources, cancels cleanly, and guards repeated requests',async({page})=>{
  const bodies:unknown[]=[];const keys:string[]=[];
  await page.route('**/api/v2/jobs',async route=>{
    if(route.request().method()!=='POST') return route.fallback();
    bodies.push(route.request().postDataJSON());keys.push(route.request().headers()['idempotency-key']);
    await new Promise(resolve=>setTimeout(resolve,400));
    await route.fulfill({status:202,contentType:'application/json',body:JSON.stringify({job_id:'job-1',state:'queued'})});
  });
  await page.goto('/broadcasts/broadcast-1');await page.getByRole('button',{name:'조각 합치기'}).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  expect(await page.locator('.merge-preview li').allTextContents()).toEqual([expect.stringContaining('live-segment-1.ts'),expect.stringContaining('live-segment-2.ts')]);
  await expect(page.getByText('아래 순서로 합친 새 결과물을 만듭니다. 원본 파일은 삭제하거나 덮어쓰지 않습니다.')).toBeVisible();
  await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).toHaveCount(0);expect(bodies).toEqual([]);
  await page.getByRole('button',{name:'조각 합치기'}).click();await page.getByRole('button',{name:'돌아가기',exact:true}).click();
  expect(bodies).toEqual([]);await page.getByRole('button',{name:'조각 합치기'}).click();
  await page.getByRole('button',{name:'작업 요청',exact:true}).evaluate(button=>{(button as HTMLButtonElement).click();(button as HTMLButtonElement).click();});
  await expect(page.getByText('작업이 접수되었습니다.')).toBeVisible();
  await expect(page.locator('.lar-toast')).toHaveCount(0);
  expect(bodies).toEqual([{kind:'merge',target_id:'broadcast-1',input_revision:detail.revision,options:{}}]);expect(keys[0]).toBeTruthy();
  await page.getByRole('link',{name:'작업 보기'}).click();await expect(page).toHaveURL(/\/jobs\?selected=job-1$/);await expect(page.getByRole('dialog')).toBeVisible();
});

test('409 refreshes broadcast revision and explains the failure without false success',async({page})=>{
  let revision=detail.revision;
  await page.route('**/api/v2/broadcasts/broadcast-1',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({...detail,revision,observed_at:now+revision})}));
  await page.route('**/api/v2/jobs',route=>{
    if(route.request().method()!=='POST') return route.fallback();
    revision++;return route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({code:'REVISION_CONFLICT',message:'Broadcast changed elsewhere',request_id:'req-409'})});
  });
  await page.goto('/broadcasts/broadcast-1');await page.getByRole('button',{name:'조각 합치기'}).click();await page.getByRole('button',{name:'작업 요청',exact:true}).click();
  await expect(page.getByText('다른 곳에서 상태가 바뀌었습니다')).toBeVisible();await expect(page.getByText(/req-409/)).toBeVisible();
  await expect(page.getByText('작업이 접수되었습니다.')).toHaveCount(0);await expect(page.getByRole('button',{name:'작업 요청',exact:true})).toBeEnabled();
});

test('connection loss retains observed library data with a stale warning',async({page})=>{
  await page.goto('/broadcasts');await expect(page.getByRole('link',{name:broadcast.title})).toBeVisible();
  await page.route('**/api/v2/broadcasts?*',route=>route.abort('internetdisconnected'));
  await page.getByRole('button',{name:'모든 상태 새로고침'}).click();
  await expect(page.getByText('갱신 중단 · 마지막 확인 데이터')).toBeVisible({timeout:10000});
  await expect(page.locator('.lar-toast')).toHaveCount(0);
  await expect(page.getByRole('link',{name:broadcast.title})).toBeVisible();
});

test('cancelled job confirmation sends nothing; actual cancel stays pending until observed',async({page})=>{
  let requests=0,cancelled=false;
  await page.route('**/api/v2/jobs/job-1/cancel',async route=>{requests++;cancelled=true;await route.fulfill({status:202,contentType:'application/json',body:JSON.stringify({...job,state:'cancel_requested',revision:3})});});
  await page.route('**/api/v2/jobs/job-1',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({...job,state:cancelled?'cancel_requested':'running',revision:cancelled?3:2,attempt_history:[]})}));
  await page.goto('/jobs?selected=job-1');await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button',{name:'작업 취소',exact:true}).click();await page.getByRole('button',{name:'돌아가기',exact:true}).click();expect(requests).toBe(0);
  await page.getByRole('button',{name:'작업 취소',exact:true}).click();await page.getByRole('button',{name:'취소 요청',exact:true}).click();
  await expect(page.getByText('프로세스가 종료되었는지 확인 중입니다. 아직 취소 완료 상태가 아닙니다.')).toBeVisible();expect(requests).toBe(1);
  await page.getByRole('button',{name:'닫기',exact:true}).last().click();await expect(page.getByRole('dialog')).toHaveCount(0);await expect(page).not.toHaveURL(/selected=/);
  await page.goBack();await expect(page.getByRole('dialog')).toBeVisible();await page.goForward();await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('job filters survive dialog dismissal and failed job retry waits for server state',async({page})=>{
  let retried=false;let requests=0;
  await page.route('**/api/v2/jobs/job-1',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({...job,state:retried?'queued':'failed',revision:retried?3:2,error_code:retried?'':'STORAGE_UNAVAILABLE',attempt_history:[]})}));
  await page.route('**/api/v2/jobs/job-1/retry',async route=>{requests++;retried=true;await route.fulfill({contentType:'application/json',body:JSON.stringify({...job,state:'queued',revision:3})});});
  await page.goto('/jobs');await page.getByRole('button',{name:'실패',exact:true}).click();await page.getByLabel('작업 종류').selectOption('verify');
  await expect(page).toHaveURL(/state=failed&kind=verify/);await page.locator('.job-row').click();
  await expect(page.getByText('저장소 연결, 마운트와 여유 공간을 확인한 후 재시도하세요.')).toBeVisible();
  await page.getByRole('button',{name:'재시도',exact:true}).click();await page.getByRole('button',{name:'재시도 요청',exact:true}).click();
  await expect(page.getByText('재시도 요청을 접수했습니다. 다음 시도 결과를 기다립니다.')).toBeVisible();expect(requests).toBe(1);
  await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).toHaveCount(0);await expect(page).toHaveURL(/\/jobs\?state=failed&kind=verify$/);
});

test('durable-disabled mode leaves history visible and exposes no writable job controls',async({page})=>{
  const writes:string[]=[];page.on('request',request=>{if(request.url().includes('/api/v2/')&&request.method()!=='GET')writes.push(request.url());});
  await page.route('**/api/v2/broadcasts/broadcast-1',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({...detail,jobs_available:false,artifacts:detail.artifacts.map(file=>({...file,controls_available:false})),jobs:[]})}));
  await page.route('**/api/v2/jobs?*',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({items:[],available:false,observed_at:now})}));
  await page.goto('/broadcasts/broadcast-1');await expect(page.locator('#root h1')).toHaveText(broadcast.title);
  await expect(page.getByText('파일 작업 기능이 꺼져 있습니다.')).toBeVisible();
  await expect(page.getByRole('button',{name:'조각 합치기'})).toBeDisabled();
  for(const button of await page.getByRole('button',{name:/^(검증|복구본)$/}).all()) await expect(button).toBeDisabled();
  await page.goto('/jobs?selected=job-1');await expect(page.getByText('파일 작업 기능이 꺼져 있습니다',{exact:true})).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(0);await expect(page.getByRole('button',{name:'작업 취소'})).toHaveCount(0);expect(writes).toEqual([]);
});
