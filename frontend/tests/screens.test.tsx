import { afterEach, beforeAll, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App } from '../src/App';
import { RouterProvider } from '../src/router';
import { broadcast, channel, detail, job, now, systemStatus } from './browser/fixtures';

let client: QueryClient;
const response = (data: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(data), { status, headers: {'Content-Type':'application/json'} }));
function defaultResponse(path: string) {
  if (path === '/status') return systemStatus;
  if (path === '/channels') return {items:[channel],observed_at:now,next_cursor:null};
  if (path.startsWith('/broadcasts?')) return {items:[broadcast],observed_at:now,next_cursor:null};
  if (path === '/broadcasts/broadcast-1') return detail;
  if (path.startsWith('/jobs?')) return {items:[job],observed_at:now,next_cursor:null};
  if (path === '/jobs/job-1') return {...job,attempt_history:[]};
  if (path.startsWith('/commands/')) return {id:'command-1',state:'accepted'};
  if (path === '/settings') return {enabled:true,storage:{originals_preserved:true},features:{durable_jobs:true,legacy_ui:true},links:{configuration:'/config',operations:'/operations'}};
  return {};
}
function mock(overrides?: (path: string, init?: RequestInit) => Promise<Response> | undefined) {
  const fetch = vi.fn((url: string, init?: RequestInit) => {
    const path=url.replace('/api/v2','');
    return overrides?.(path,init) || response(defaultResponse(path));
  });
  vi.stubGlobal('fetch',fetch);return fetch;
}
function mount(path: string) {
  history.replaceState(null,'',path);
  client = new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});
  render(<QueryClientProvider client={client}><RouterProvider><App/></RouterProvider></QueryClientProvider>);
}
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function(){this.setAttribute('open','');};
  HTMLDialogElement.prototype.close = function(){this.removeAttribute('open');};
});
afterEach(()=>{cleanup();client?.clear();vi.unstubAllGlobals();});

it.each([['/v2','녹화 현황'],['/v2/broadcasts','방송 보관함'],['/v2/channels','채널'],['/v2/jobs','작업'],['/v2/settings','설정'],['/v2/broadcasts/broadcast-1',broadcast.title]])('renders %s with actual API fixture fields',async(path,title)=>{
  mock();mount(path);await waitFor(()=>expect(screen.getByRole('heading',{name:title,level:1})).toBeTruthy());
  await waitFor(()=>expect(screen.getByText('서버 연결됨')).toBeTruthy());
  expect(screen.queryByText('화면을 표시하지 못했습니다.')).toBeNull();
});
it('keeps select labels separate from their option text',async()=>{
  mock();mount('/v2/broadcasts');await screen.findByRole('option',{name:channel.name});
  for (const name of ['플랫폼','채널','방송 상태']) {
    const select=screen.getByRole('combobox',{name}) as HTMLSelectElement;
    expect(select.labels).toHaveLength(1);
    // Playwright's exact getByLabel reads the full native label text.
    expect(select.labels?.[0].textContent).toBe(name);
    expect(screen.getByLabelText(name,{exact:true})).toBe(select);
  }
});
it('persists search, select and UTC date filters in URL and API requests',async()=>{
  const fetch=mock();mount('/v2/broadcasts');await screen.findByRole('heading',{name:'방송 보관함',level:1});
  fireEvent.change(screen.getByRole('searchbox',{name:'방송 제목 검색'}),{target:{value:'가을'}});
  fireEvent.change(screen.getByLabelText('플랫폼',{exact:true}),{target:{value:'chzzk'}});
  await screen.findByRole('option',{name:channel.name});
  fireEvent.change(screen.getByLabelText('채널',{exact:true}),{target:{value:channel.id}});
  fireEvent.change(screen.getByLabelText('방송 상태',{exact:true}),{target:{value:'completed'}});
  fireEvent.change(screen.getByLabelText('시작일 (UTC)'),{target:{value:'2026-10-01'}});
  fireEvent.change(screen.getByLabelText('종료일 (UTC)'),{target:{value:'2026-10-11'}});
  const filters={query:'가을',platform:'chzzk',channel_id:channel.id,status:'completed',date_from:'2026-10-01',date_to:'2026-10-11'};
  expect(Object.fromEntries(new URLSearchParams(location.search))).toEqual(filters);
  await waitFor(()=>expect(fetch.mock.calls.some(([url])=>{
    const params=new URL(url,location.origin).searchParams;
    return Object.entries(filters).every(([key,value])=>params.get(key)===value);
  })).toBe(true));
});
it('closes a command confirmation without sending a command',async()=>{
  const fetch=mock();mount('/v2/channels');await screen.findByRole('heading',{name:channel.name});
  fireEvent.click(screen.getByRole('button',{name:'지금 한 번 녹화'}));
  expect(screen.getByRole('dialog')).toBeTruthy();fireEvent.click(screen.getByRole('button',{name:'돌아가기'}));
  expect(screen.queryByRole('dialog')).toBeNull();expect(fetch.mock.calls.some(([,options])=>options?.method==='POST')).toBe(false);
});
it('never paints recording or resends while a command is accepted',async()=>{
  let finish!:(value:Response)=>void;
  const fetch=mock((path)=>path==='/channels/ch-1/commands'?new Promise(resolve=>{finish=resolve;}):undefined);
  mount('/v2/channels');await screen.findByRole('heading',{name:channel.name});
  fireEvent.click(screen.getByRole('button',{name:'지금 한 번 녹화'}));
  fireEvent.click(screen.getByRole('button',{name:'한 번 녹화 요청'}));
  fireEvent.click(screen.getByRole('button',{name:'명령 전송 중…'}));
  expect(fetch.mock.calls.filter(([path])=>path.endsWith('/commands'))).toHaveLength(1);
  finish(new Response(JSON.stringify({command_id:'command-1',state:'accepted'}),{status:202}));
  await screen.findByText('명령 접수 · 실제 처리 결과를 기다리는 중입니다.');
  expect(screen.getByText('감시 중',{selector:'.channel-states .badge'})).toBeTruthy();
  expect(screen.queryByText('녹화 중',{selector:'.channel-states .badge'})).toBeNull();
  expect((screen.getByRole('button',{name:'명령 처리 중…'}) as HTMLButtonElement).disabled).toBe(true);
});
it('shows blocked command reason and releases its pending state',async()=>{
  mock(path=>path==='/channels/ch-1/commands'?response({command_id:'command-1',state:'blocked',error_code:'STORAGE_UNAVAILABLE'},202):path==='/commands/command-1'?response({id:'command-1',state:'blocked',error_code:'STORAGE_UNAVAILABLE'}):undefined);
  mount('/v2/channels');await screen.findByRole('heading',{name:channel.name});
  fireEvent.click(screen.getByRole('button',{name:'지금 한 번 녹화'}));fireEvent.click(screen.getByRole('button',{name:'한 번 녹화 요청'}));
  await screen.findByText(/명령 오류 · STORAGE_UNAVAILABLE/);
  expect((screen.getByRole('button',{name:'지금 한 번 녹화'}) as HTMLButtonElement).disabled).toBe(false);
});
it('a running once request still permits stopping an observed recording',async()=>{
  let recording=false;
  mock(path=>path==='/channels'?response({items:[recording?{...channel,actual_state:'recording',broadcast_id:'broadcast-1',revision:5}:channel],observed_at:now+1}):path==='/channels/ch-1/commands'?(recording=true,response({command_id:'command-1',state:'running'},202)):path==='/commands/command-1'?response({id:'command-1',state:'running'}):undefined);
  mount('/v2/channels');await screen.findByRole('heading',{name:channel.name});fireEvent.click(screen.getByRole('button',{name:'지금 한 번 녹화'}));fireEvent.click(screen.getByRole('button',{name:'한 번 녹화 요청'}));
  const stop=await screen.findByRole('button',{name:'이번 방송 중지'});expect((stop as HTMLButtonElement).disabled).toBe(false);
});
it('a revision conflict refetches and explains the latest state',async()=>{
  let changed=false;
  mock(path=>path==='/channels/ch-1'?(changed=true,response({code:'REVISION_CONFLICT',message:'changed',request_id:'r409'},409)):path==='/channels'?response({items:[changed?{...channel,desired_mode:'paused',revision:5}:channel],observed_at:now+1}):undefined);
  mount('/v2/channels');await screen.findByRole('heading',{name:channel.name});fireEvent.click(screen.getByRole('button',{name:'자동 녹화 끄기'}));
  await screen.findByText('다른 곳에서 상태가 바뀌었습니다');await screen.findByRole('button',{name:'자동 녹화 켜기'});
  expect(screen.getByText(/r409/)).toBeTruthy();
});
it('merge preview preserves order and submits the observed detail revision',async()=>{
  const fetch=mock((path,init)=>path==='/jobs'&&init?.method==='POST'?response({job_id:'merged-job'},202):undefined);
  mount('/v2/broadcasts/broadcast-1');await screen.findByRole('heading',{name:broadcast.title,level:1});fireEvent.click(screen.getByRole('button',{name:'조각 합치기'}));
  const dialog=screen.getByRole('dialog');const files=within(dialog).getAllByRole('listitem');
  expect(files[0].textContent).toContain('segment-1.ts');expect(files[1].textContent).toContain('segment-2.ts');
  fireEvent.click(within(dialog).getByRole('button',{name:'작업 요청'}));await screen.findByText('작업이 접수되었습니다.');
  const post=fetch.mock.calls.find(([,init])=>init?.method==='POST');expect(JSON.parse(post?.[1]?.body as string)).toEqual({kind:'merge',target_id:'broadcast-1',input_revision:detail.revision,options:{}});
});
it('job cancellation distinguishes requested from actual termination',async()=>{
  let requested=false;
  mock(path=>path==='/jobs/job-1/cancel'?(requested=true,response({...job,state:'cancel_requested',revision:3},202)):path==='/jobs/job-1'?response({...job,state:requested?'cancel_requested':'running',revision:requested?3:2,attempt_history:[]}):undefined);
  mount('/v2/jobs?selected=job-1');await screen.findByRole('button',{name:'작업 취소'});
  fireEvent.click(screen.getByRole('button',{name:'작업 취소'}));fireEvent.click(screen.getByRole('button',{name:'취소 요청'}));
  await screen.findByText('프로세스가 종료되었는지 확인 중입니다. 아직 취소 완료 상태가 아닙니다.');
  expect(screen.queryByText('취소됨')).toBeNull();
});
it('storage errors and last-good timestamp survive screen navigation',async()=>{
  mock(path=>path==='/status'?response({...systemStatus,storage:{status:'blocked',message:'NAS unavailable',last_ok_at:now-300}}):undefined);
  mount('/v2');await screen.findByText('NAS unavailable');
  fireEvent.click(within(screen.getByRole('navigation',{name:'주 메뉴'})).getByRole('link',{name:'방송 보관함'}));
  await screen.findByRole('heading',{name:'방송 보관함',level:1});expect(screen.getByText('NAS unavailable')).toBeTruthy();expect(screen.getByText(/마지막 정상 확인 2026/)).toBeTruthy();
});

function compatibilityMock(overrides?: (path: string, init?: RequestInit) => Promise<Response> | undefined) {
  return mock((path, init) => {
    const overridden = overrides?.(path, init);
    if (overridden) return overridden;
    if (path === '/status') return response({...systemStatus,features:{durable_jobs:false,channel_controls:false},worker:{ready:false},storage:{status:'unknown'}});
    if (path === '/channels') return response({items:[{...channel,controls_available:false}],observed_at:now,next_cursor:null});
    if (path.startsWith('/jobs?')) return response({items:[],observed_at:now,next_cursor:null,available:false});
    if (path === '/broadcasts/broadcast-1') return response({...detail,jobs_available:false,jobs:[],artifacts:detail.artifacts.map(artifact=>({...artifact,controls_available:false,exists:undefined,exists_status:'unknown',validation:null}))});
    if (path === '/settings') return response({enabled:true,features:{durable_jobs:false,legacy_ui:true}});
  });
}
it('root is the active overview and compatibility status does not invent worker or storage health',async()=>{
  compatibilityMock();mount('/');await screen.findByRole('heading',{name:'녹화 현황',level:1});
  await screen.findByText('저장소 미확인');
  expect(screen.queryByText('작업 실행기가 준비되지 않았습니다.')).toBeNull();
  expect(screen.queryByText('작업 목록에서 조치 대상을 찾지 못했습니다')).toBeNull();
  expect(screen.getByText('파일 작업 기능이 꺼져 있습니다')).toBeTruthy();
  const nav=within(screen.getByRole('navigation',{name:'주 메뉴'}));
  expect(nav.getByRole('link',{name:'현황'}).getAttribute('aria-current')).toBe('page');
  expect(screen.getByRole('link',{name:'기존 화면으로 이동'}).getAttribute('href')).toBe('/legacy');
  expect(document.title).toBe('현황 · Live Auto Recorder');
});
it('compatibility overview displays live observations and links to the catalog detail',async()=>{
  compatibilityMock(path=>path==='/channels'?response({items:[{...channel,controls_available:false,actual_state:'recording',title:broadcast.title,broadcast_id:broadcast.id}],observed_at:now}):undefined);
  mount('/v2');await screen.findByRole('heading',{name:broadcast.title});
  expect(screen.getByRole('link',{name:'상세 보기'}).getAttribute('href')).toBe('/v2/broadcasts/broadcast-1');
});
it('compatibility controls use legacy semantics and cancelling a confirmation sends nothing',async()=>{
  const fetch=compatibilityMock();mount('/v2/channels');await screen.findByRole('heading',{name:channel.name});
  expect(screen.queryByRole('button',{name:'지금 한 번 녹화'})).toBeNull();
  expect(screen.queryByRole('button',{name:'자동 녹화 끄기'})).toBeNull();
  expect(screen.queryByText('자동 녹화를 꺼도 현재 방송은 계속 녹화됩니다.')).toBeNull();
  expect(screen.getByRole('link',{name:'자동 녹화 설정'}).getAttribute('href')).toBe('/channels');
  fireEvent.click(screen.getByRole('button',{name:'녹화 시작'}));
  fireEvent.click(screen.getByRole('button',{name:'돌아가기'}));
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(fetch.mock.calls.some(([,init])=>init?.method==='POST')).toBe(false);
});
it('compatibility start is sent once while pending and acknowledged without optimistic recording',async()=>{
  let finish!:(value:Response)=>void;
  const fetch=compatibilityMock(path=>path==='/api/start_recording/ch-1'?new Promise(resolve=>{finish=resolve;}):undefined);
  mount('/v2/channels');await screen.findByRole('heading',{name:channel.name});
  fireEvent.click(screen.getByRole('button',{name:'녹화 시작'}));
  fireEvent.click(screen.getByRole('button',{name:'녹화 시작 요청'}));
  fireEvent.click(screen.getByRole('button',{name:'요청 전송 중…'}));
  fireEvent.click(screen.getByRole('button',{name:'닫기'}));
  expect(screen.getByRole('dialog')).toBeTruthy();
  expect(fetch.mock.calls.filter(([,init])=>init?.method==='POST')).toHaveLength(1);
  const post=fetch.mock.calls.find(([,init])=>init?.method==='POST');
  expect(post?.[0]).toBe('/api/start_recording/ch-1');
  expect(JSON.parse(post?.[1]?.body as string)).toEqual({is_user_request:true});
  expect((post?.[1]?.headers as Record<string,string>)['Idempotency-Key']).toBeUndefined();
  finish(new Response(JSON.stringify({status:'success',state:'녹화 중'})));
  await screen.findByText('녹화 시작 요청을 접수했습니다. 실제 상태는 새 관측 결과로 확인하세요.');
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(screen.getByText('감시 중',{selector:'.channel-states .badge'})).toBeTruthy();
  expect(screen.queryByText('녹화 중',{selector:'.channel-states .badge'})).toBeNull();
  expect(fetch.mock.calls.filter(([url])=>url==='/api/v2/channels').length).toBeGreaterThan(1);
  expect(fetch.mock.calls.filter(([url])=>url==='/api/v2/status').length).toBeGreaterThan(1);
});
it('compatibility stop works without a durable broadcast ID and keeps observed recording until refreshed',async()=>{
  const fetch=compatibilityMock(path=>path==='/channels'?response({items:[{...channel,controls_available:false,actual_state:'recording',broadcast_id:null}],observed_at:now}):path==='/api/stop_recording/ch-1'?response({status:'success',state:'대기 중'}):undefined);
  mount('/v2/channels');await screen.findByRole('button',{name:'녹화 중지'});
  expect(screen.queryByRole('button',{name:'이번 방송 중지'})).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'녹화 중지'}));
  fireEvent.click(screen.getByRole('button',{name:'녹화 중지 요청'}));
  await screen.findByText('녹화 중지 요청을 접수했습니다. 실제 상태는 새 관측 결과로 확인하세요.');
  const post=fetch.mock.calls.find(([,init])=>init?.method==='POST');
  expect(post?.[0]).toBe('/api/stop_recording/ch-1');expect(post?.[1]?.body).toBeUndefined();
  expect(screen.getByText('녹화 중',{selector:'.channel-states .badge'})).toBeTruthy();
});
it('compatibility network failure is surfaced and refreshes observations without replaying a request',async()=>{
  const fetch=compatibilityMock(path=>path==='/api/start_recording/ch-1'?Promise.reject(new TypeError('connection lost')):undefined);
  mount('/v2/channels');await screen.findByRole('button',{name:'녹화 시작'});
  fireEvent.click(screen.getByRole('button',{name:'녹화 시작'}));fireEvent.click(screen.getByRole('button',{name:'녹화 시작 요청'}));
  await screen.findByText('CONNECTION_LOST');
  await waitFor(()=>expect((screen.getByRole('button',{name:'녹화 시작 요청'}) as HTMLButtonElement).disabled).toBe(false));
  expect(screen.queryByText(/요청을 접수했습니다/)).toBeNull();
  expect(fetch.mock.calls.filter(([,init])=>init?.method==='POST')).toHaveLength(1);
  expect(fetch.mock.calls.filter(([url])=>url==='/api/v2/channels').length).toBeGreaterThan(1);
});
it('compatibility file actions are disabled while unknown artifacts remain unverified',async()=>{
  const fetch=compatibilityMock();mount('/v2/broadcasts/broadcast-1');await screen.findByRole('heading',{name:broadcast.title,level:1});
  for(const button of screen.getAllByRole('button').filter(button=>['검증','복구본','조각 합치기'].includes(button.textContent || ''))) {
    expect((button as HTMLButtonElement).disabled).toBe(true);fireEvent.click(button);
  }
  expect(screen.getAllByText(/파일 존재 여부 미확인/)).toHaveLength(detail.artifacts.length);
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(fetch.mock.calls.some(([,init])=>init?.method==='POST')).toBe(false);
  expect(screen.getByText('파일 작업 기능이 꺼져 있습니다.')).toBeTruthy();
});
it('artifact-level unavailable controls are honored even when broadcast jobs availability is absent',async()=>{
  mock(path=>path==='/broadcasts/broadcast-1'?response({...detail,artifacts:detail.artifacts.map(artifact=>({...artifact,controls_available:false}))}):undefined);
  mount('/v2/broadcasts/broadcast-1');await screen.findByRole('heading',{name:broadcast.title,level:1});
  for(const name of ['검증','복구본','조각 합치기']) for(const button of screen.getAllByRole('button',{name})) expect((button as HTMLButtonElement).disabled).toBe(true);
});
it('disabled jobs mode is explicit and stale selected links never load unavailable job details',async()=>{
  const fetch=compatibilityMock();mount('/v2/jobs?selected=old-job');await screen.findByText('파일 작업 기능이 꺼져 있습니다');
  expect(screen.queryByText('조건에 맞는 작업이 없습니다')).toBeNull();
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(fetch.mock.calls.some(([url])=>url.includes('/jobs/old-job'))).toBe(false);
  expect(screen.getByRole('link',{name:'기존 파일 탐색'}).getAttribute('href')).toBe('/files');
});
it('settings distinguishes disabled durable features and links to the preserved legacy dashboard',async()=>{
  compatibilityMock();mount('/v2/settings');await screen.findByText('사용 안 함');
  expect(screen.getByRole('link',{name:'기존 녹화 화면으로 이동'}).getAttribute('href')).toBe('/legacy');
  expect(screen.getByRole('link',{name:'채널 설정'}).getAttribute('href')).toBe('/channels');
});
