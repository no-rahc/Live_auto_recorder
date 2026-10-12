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
