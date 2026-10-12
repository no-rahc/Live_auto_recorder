import { afterEach, beforeAll, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App } from '../src/App';
import { RouterProvider } from '../src/router';
import { broadcast, channel, detail, job, now } from './browser/fixtures';

let client: QueryClient;
const response = (data: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(data), { status, headers: {'Content-Type':'application/json'} }));
function defaultResponse(path: string) {
  if (path === '/channels') return {items:[channel],observed_at:now,next_cursor:null};
  if (path.startsWith('/broadcasts?')) return {items:[broadcast],observed_at:now,next_cursor:null};
  if (path === '/broadcasts/broadcast-1') return detail;
  if (path.startsWith('/jobs?')) return {items:[job],observed_at:now,next_cursor:null};
  if (path === '/jobs/job-1') return {...job,attempt_history:[]};
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

it.each([['/broadcasts','방송 보관함'],['/jobs','작업 상태'],['/broadcasts/broadcast-1',broadcast.title]])('renders the embedded %s screen without a replacement shell',async(path,title)=>{
  mock();mount(path);await waitFor(()=>expect(screen.getByRole('heading',{name:title,level:1})).toBeTruthy());
  expect(screen.queryByText('화면을 표시하지 못했습니다.')).toBeNull();
  expect(screen.queryByRole('navigation')).toBeNull();
  expect(document.querySelector('.sidebar, .app-layout, .mobile-nav')).toBeNull();
});
it('keeps select labels separate from their option text',async()=>{
  mock();mount('/broadcasts');await screen.findByRole('option',{name:channel.name});
  for (const name of ['플랫폼','채널','방송 상태']) {
    const select=screen.getByRole('combobox',{name}) as HTMLSelectElement;
    expect(select.labels).toHaveLength(1);
    // Playwright's exact getByLabel reads the full native label text.
    expect(select.labels?.[0].textContent).toBe(name);
    expect(screen.getByLabelText(name,{exact:true})).toBe(select);
  }
});
it('persists search, select and UTC date filters in URL and API requests',async()=>{
  const fetch=mock();mount('/broadcasts');await screen.findByRole('heading',{name:'방송 보관함',level:1});
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
it('closes a merge confirmation without sending a job',async()=>{
  const fetch=mock();mount('/broadcasts/broadcast-1');await screen.findByRole('heading',{name:broadcast.title});
  fireEvent.click(screen.getByRole('button',{name:'조각 합치기'}));
  expect(screen.getByRole('dialog')).toBeTruthy();fireEvent.click(screen.getByRole('button',{name:'돌아가기'}));
  expect(screen.queryByRole('dialog')).toBeNull();expect(fetch.mock.calls.some(([,options])=>options?.method==='POST')).toBe(false);
});
it('deduplicates repeated merge confirmation clicks until its observed response',async()=>{
  let finish!:(response:Response)=>void;
  const fetch=mock((path,init)=>path==='/jobs'&&init?.method==='POST'?new Promise(resolve=>{finish=resolve;}):undefined);
  mount('/broadcasts/broadcast-1');await screen.findByRole('heading',{name:broadcast.title});
  fireEvent.click(screen.getByRole('button',{name:'조각 합치기'}));
  const button=screen.getByRole('button',{name:'작업 요청'});fireEvent.click(button);fireEvent.click(button);
  expect(fetch.mock.calls.filter(([,init])=>init?.method==='POST')).toHaveLength(1);
  expect((button as HTMLButtonElement).disabled).toBe(true);
  expect(screen.queryByText('작업이 접수되었습니다.')).toBeNull();
  finish(new Response(JSON.stringify({job_id:'job-1',state:'queued'}),{status:202}));
  await screen.findByText('작업이 접수되었습니다.');
  expect(screen.getByRole('link',{name:'작업 보기'}).getAttribute('href')).toBe('/jobs?selected=job-1');
});
it('a revision conflict refreshes broadcast data without showing success',async()=>{
  let changed=false;
  const fetch=mock((path,init)=>path==='/jobs'&&init?.method==='POST'?(changed=true,response({code:'REVISION_CONFLICT',message:'changed',request_id:'r409'},409)):path==='/broadcasts/broadcast-1'?response({...detail,revision:changed?4:3,observed_at:now+(changed?1:0)}):undefined);
  mount('/broadcasts/broadcast-1');await screen.findByRole('heading',{name:broadcast.title});
  fireEvent.click(screen.getByRole('button',{name:'조각 합치기'}));fireEvent.click(screen.getByRole('button',{name:'작업 요청'}));
  await screen.findByText('다른 곳에서 상태가 바뀌었습니다');expect(screen.getByText(/r409/)).toBeTruthy();
  expect(screen.queryByText('작업이 접수되었습니다.')).toBeNull();
  await waitFor(()=>expect(fetch.mock.calls.filter(([path])=>path.endsWith('/broadcasts/broadcast-1')).length).toBeGreaterThan(1));
});
it('merge preview preserves order and submits the observed detail revision',async()=>{
  const fetch=mock((path,init)=>path==='/jobs'&&init?.method==='POST'?response({job_id:'merged-job'},202):undefined);
  mount('/broadcasts/broadcast-1');await screen.findByRole('heading',{name:broadcast.title,level:1});fireEvent.click(screen.getByRole('button',{name:'조각 합치기'}));
  const dialog=screen.getByRole('dialog');const files=within(dialog).getAllByRole('listitem');
  expect(files[0].textContent).toContain('segment-1.ts');expect(files[1].textContent).toContain('segment-2.ts');
  fireEvent.click(within(dialog).getByRole('button',{name:'작업 요청'}));await screen.findByText('작업이 접수되었습니다.');
  const post=fetch.mock.calls.find(([,init])=>init?.method==='POST');expect(JSON.parse(post?.[1]?.body as string)).toEqual({kind:'merge',target_id:'broadcast-1',input_revision:detail.revision,options:{}});
});
it('job cancellation distinguishes requested from actual termination',async()=>{
  let requested=false;
  mock(path=>path==='/jobs/job-1/cancel'?(requested=true,response({...job,state:'cancel_requested',revision:3},202)):path==='/jobs/job-1'?response({...job,state:requested?'cancel_requested':'running',revision:requested?3:2,attempt_history:[]}):undefined);
  mount('/jobs?selected=job-1');await screen.findByRole('button',{name:'작업 취소'});
  fireEvent.click(screen.getByRole('button',{name:'작업 취소'}));fireEvent.click(screen.getByRole('button',{name:'취소 요청'}));
  await screen.findByText('프로세스가 종료되었는지 확인 중입니다. 아직 취소 완료 상태가 아닙니다.');
  expect(screen.queryByText('취소됨')).toBeNull();
});
it('keeps last library data visible when a refresh loses the connection',async()=>{
  let offline=false;
  mock(path=>path.startsWith('/broadcasts?')&&offline?Promise.reject(new TypeError('connection lost')):undefined);
  mount('/broadcasts');await screen.findByRole('link',{name:broadcast.title});offline=true;
  fireEvent.click(screen.getByRole('button',{name:'모든 상태 새로고침'}));
  await screen.findByText('갱신 중단 · 마지막 확인 데이터',{}, {timeout:5000});
  expect(screen.getByRole('link',{name:broadcast.title})).toBeTruthy();
});
it('shows a request-specific initial error and can retry to real data',async()=>{
  let failed=true;
  mock(path=>path.startsWith('/broadcasts?')&&failed?response({code:'STORAGE_UNAVAILABLE',message:'Storage check failed',request_id:'r503'},503):undefined);
  mount('/broadcasts');await screen.findByText('Storage check failed',{}, {timeout:5000});
  expect(screen.getByText(/r503/)).toBeTruthy();failed=false;
  fireEvent.click(screen.getByRole('button',{name:'다시 확인'}));await screen.findByRole('link',{name:broadcast.title});
});
it('leaves original history visible but disables all file mutations without durable jobs',async()=>{
  const fetch=mock(path=>path==='/broadcasts/broadcast-1'?response({...detail,jobs_available:false,artifacts:detail.artifacts.map(file=>({...file,controls_available:false}))}):undefined);
  mount('/broadcasts/broadcast-1');await screen.findByRole('heading',{name:broadcast.title});
  expect(screen.getByText('파일 작업 기능이 꺼져 있습니다.')).toBeTruthy();
  const merge=screen.getByRole('button',{name:'조각 합치기'}) as HTMLButtonElement;expect(merge.disabled).toBe(true);fireEvent.click(merge);
  expect(screen.queryByRole('dialog')).toBeNull();expect(fetch.mock.calls.some(([,init])=>init?.method==='POST')).toBe(false);
});
it('never requests job details or exposes cancellation when the queue is disabled',async()=>{
  const fetch=mock(path=>path.startsWith('/jobs?')?response({items:[],available:false,observed_at:now}):undefined);
  mount('/jobs?selected=job-1');await screen.findByText('파일 작업 기능이 꺼져 있습니다');
  expect(screen.queryByRole('dialog')).toBeNull();expect(screen.queryByRole('button',{name:'작업 취소'})).toBeNull();
  expect(fetch.mock.calls.some(([path])=>path.endsWith('/jobs/job-1'))).toBe(false);
});

it('does not imply existing legacy merge outputs are absent when unavailable',async()=>{
  mock(path=>path==='/broadcasts/broadcast-1'?response({...detail,jobs_available:false,artifacts:detail.artifacts.filter(file=>file.kind==='original'),jobs:[]}):undefined);
  mount('/broadcasts/broadcast-1');
  await screen.findByText('기존 결과물은 파일 관리에서 확인하세요');
  expect(screen.queryByText('아직 만들어진 결과물이 없습니다')).toBeNull();
  expect(screen.getByRole('link',{name:'결과 파일 찾기'}).getAttribute('href')).toBe('/files');
});
