import type { Page } from '@playwright/test';
export const now = 1791727200;
export const channel = {id:'ch-1',name:'초록 스튜디오',platform:'chzzk',desired_mode:'auto',actual_state:'watching',revision:4,observed_at:now,reason_code:'',broadcast_id:null};
export const broadcast = {id:'broadcast-1',title:'가을 저녁의 작업실, 길고 조용한 라이브 방송',channel_id:'ch-1',channel_name:'초록 스튜디오',platform:'chzzk',started_at:'2026-10-11T09:00:00Z',ended_at:'2026-10-11T12:00:00Z',status:'completed',segment_count:2,total_size:2400000000,duration_seconds:10500,validation_status:'valid',revision:3,observed_at:now};
export const originals = [1,2].map(i=>({id:`legacy-recording-${i}`,broadcast_id:'broadcast-1',segment_id:`segment-${i}`,revision:i+2,kind:'original',relative_path:`초록 스튜디오/2026-10-11/live-segment-${i}.ts`,size:1200000000,validation:'valid',exists_status:'present',storage_id:'legacy'}));
export const job = {id:'job-1',kind:'verify',target_id:'legacy-recording-1',state:'running',attempts:1,max_attempts:5,progress:{stage:'ffprobe',percent:35},created_at:now-100,observed_at:now,revision:2,error_code:'',error_message:'',next_run_at:now+100};
export const detail = {...broadcast,identity_basis:'heuristic',sessions:[{id:'session-1',engine:'streamlink',started_at:broadcast.started_at,ended_at:broadcast.ended_at,outcome:'completed'}],segments:[1,2].map(i=>({id:`segment-${i}`,sequence:i,captured_from:'2026-10-11T09:00:00Z',captured_to:'2026-10-11T10:30:00Z',gap_before:i===2?60:null,duration_seconds:5250})),artifacts:[...originals,{id:'merged-1',revision:1,kind:'merged',relative_path:'outputs/live-merged.mp4',size:2390000000,validation:'valid',exists:true}],jobs:[job]};
export const systemStatus = {enabled:true,version:'2.0 preview',observed_at:now,channels:{recording:0,watching:1,attention:0,total:1},jobs:{queued:0,running:1,failed:0,blocked:0},worker:{ready:true,running:1},storage:{status:'ok',free_bytes:500000000000,total_bytes:1000000000000,last_ok_at:now}};
export async function mockApi(page: Page) {
  await page.route('**/api/v2/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown = {};
    if(path==='/api/v2/status') data=systemStatus;
    else if(path==='/api/v2/channels') data={items:[channel],next_cursor:null,observed_at:now};
    else if(path==='/api/v2/broadcasts') data={items:[broadcast],next_cursor:null,observed_at:now};
    else if(path==='/api/v2/broadcasts/broadcast-1') data=detail;
    else if(path==='/api/v2/jobs') data={items:[job],next_cursor:null,observed_at:now};
    else if(path==='/api/v2/jobs/job-1') data={...job,attempt_history:[{id:'attempt-1',attempt_no:1,started_at:now-90,outcome:'running',error_detail:''}]};
    else if(path==='/api/v2/settings') data={enabled:true,version:'2.0 preview',storage:{database:'local persistent volume',recordings:'existing paths preserved',originals_preserved:true},features:{durable_jobs:true,legacy_ui:true},links:{configuration:'/config',files:'/files',operations:'/operations'}};
    else if(path.startsWith('/api/v2/commands/')) data={id:'command-1',state:'accepted',observed_at:now};
    else return route.fulfill({status:404,contentType:'application/json',body:JSON.stringify({code:'NOT_FOUND',message:'Unknown test route'})});
    await route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
  });
}

/** Only data are synthetic; serve_ui.py renders the production v1 templates/assets. */
export const metrics = {cpu_name:'Synthetic preview CPU',cpu_percent:18.4,mem_percent:38.5,mem_used:6614249635,mem_total:17179869184,net_up_bps:524288,net_down_bps:8388608,net_bytes_sent:104857600,net_bytes_recv:1073741824,disks:[{mountpoint:'/synthetic/recordings',fstype:'cifs',used:500000000000,total:1000000000000,free:500000000000,percent:50}]};
export async function mockLegacyApi(page: Page) {
  const fulfill = (data: unknown) => ({contentType:'application/json',body:JSON.stringify(data)});
  await page.route('**/api/**', async route => {
    const path=new URL(route.request().url()).pathname;
    if(path.startsWith('/api/v2/')) return route.fallback();
    const values: Record<string, unknown> = {
      '/api/config': {loginMode:false,autoRecordingMode:false},
      '/api/channels': [{...channel,channel_name:channel.name,live_title:broadcast.title}],
      '/api/sys_metrics': metrics,
      '/api/recording_history': {history:[{ts:'2026-10-11T12:00:00Z',channel_name:channel.name,event:'stop',filename:'synthetic-sample.ts',duration:'02:55:00'}],stats:{today_recordings:2,today_failures:0}},
      '/api/operations/summary': {storage:{status:'ok',free_text:'500 GB',free_percent:50}},
      '/api/operations/health': {channels:[]},
    };
    if(path in values) return route.fulfill(fulfill(values[path]));
    return route.fulfill({status:404,...fulfill({code:'NOT_FOUND',message:'No synthetic fixture for this API'})});
  });
  await page.route('**/user_info',route=>route.fulfill(fulfill({logged_in:false,username:'Synthetic preview',config:{loginMode:false}})));
  await page.route('**/status',route=>route.fulfill(fulfill({'ch-1':{recording:false,reserved:false}})));
  await page.routeWebSocket('**/ws/sys_metrics',socket=>socket.send(JSON.stringify(metrics)));
}
export async function mockConsoleApi(page: Page) {
  await mockApi(page);
  await mockLegacyApi(page);
}
