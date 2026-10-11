import { Badge, DetailLink, Empty, ErrorNotice, Icon, LastUpdated, Loading, PageHeading, Panel } from './components';
import { bytes, date, elapsed, label } from './format';
import { Link } from './router';
import { useApiQuery, useChannelsQuery } from './query';
import type { Channel, Job, Page, SystemStatus } from './types';

export function Dashboard({ status }: { status?: SystemStatus }) {
  const channels = useChannelsQuery();
  const jobs = useApiQuery<Page<Job>>('/jobs?limit=50');
  const active = (channels.data?.items || []).filter(channel => ['recording','starting','reconnecting','stopping'].includes(channel.actual_state));
  const attention = (jobs.data?.items || []).filter(job => ['failed','blocked','interrupted','retry_wait'].includes(job.state));
  const stats = [
    { label: '녹화 중', value: status?.channels.recording, caption: '지금 보관하는 방송', icon: 'channels', className: 'recording-stat' },
    { label: '감시 중', value: status?.channels.watching, caption: '다음 방송을 기다리는 채널', icon: 'clock', className: '' },
    { label: '조치 필요', value: status ? status.channels.attention + status.jobs.failed + status.jobs.blocked : undefined, caption: '확인이 필요한 채널과 작업', icon: 'warning', className: 'attention-stat' },
  ];
  return <>
    <PageHeading eyebrow="OVERVIEW" title="녹화 현황" description="지금 녹화 중인 방송과 확인이 필요한 작업을 한눈에." action={<Link to="/v2/channels" className="button primary"><Icon name="channels"/>채널 관리</Link>}/>
    <div className="stats-grid">{stats.map(stat => <div className={`stat-card ${stat.className}`} key={stat.label}><div className="stat-top"><span>{stat.label}</span><Icon name={stat.icon}/></div><strong>{stat.value ?? '—'}<span>개</span></strong><p>{stat.caption}</p></div>)}</div>
    <div className="section-gap"><Panel title="실시간 녹화" subtitle="실제 녹화 상태를 5초마다 확인합니다." action={<span className="small-label">{active.length}개 표시</span>}>
      <ErrorNotice error={channels.error} stale={Boolean(channels.data)} onRetry={() => void channels.refetch()}/>
      {channels.isPending ? <Loading/> : active.length ? <div className="recording-grid">{active.map(channel => <article className="recording-card" key={channel.id}>
        <div className="card-top"><span className={`platform-mark ${channel.platform}`}>{label(channel.platform)}</span><Badge value={channel.actual_state}/></div>
        <h3>{channel.title || channel.name}</h3><p className="muted">{channel.name}{channel.title ? '' : ' · 방송 제목 확인 대기'}</p>
        <div className="recording-signal" aria-hidden="true">{Array.from({ length: 32 }, (_, i) => <i key={i} style={{ height: `${8 + ((i * 13 + 17) % 27)}px` }}/>)}</div>
        <div className="metric-pair"><div><span>경과 시간</span><strong>{elapsed(channel.started_at)}</strong></div><div><span>기록 속도</span><strong>{channel.write_rate_bps == null ? '확인 대기' : `${bytes(channel.write_rate_bps)}/s`}</strong></div></div>
        <div className="card-footer"><small>마지막 기록 {date(channel.last_write_at, true)}</small>{channel.broadcast_id ? <DetailLink id={channel.broadcast_id}/> : <Link to="/v2/channels" className="text-link">상태 확인<Icon name="arrow" size={16}/></Link>}</div>
      </article>)}</div> : <Empty icon="channels" title="지금 녹화 중인 방송이 없습니다" action={<Link to="/v2/channels" className="button secondary">채널 확인<Icon name="arrow" size={16}/></Link>}>자동 녹화가 켜진 채널은 방송이 시작되면 녹화를 준비합니다.</Empty>}
      <LastUpdated at={channels.data?.observed_at} fetching={channels.isFetching}/>
    </Panel></div>
    <div className="dashboard-bottom"><Panel title="확인이 필요한 작업" subtitle="실패 원인을 확인하고 안전하게 다시 진행하세요." action={<Link to="/v2/jobs" className="text-link">모든 작업<Icon name="arrow" size={16}/></Link>}>
      <ErrorNotice error={jobs.error} stale={Boolean(jobs.data)} onRetry={() => void jobs.refetch()}/>
      {jobs.isPending ? <Loading/> : attention.length ? <div className="attention-list">{attention.slice(0, 5).map(job => <Link key={job.id} to={`/v2/jobs?selected=${encodeURIComponent(job.id)}`} className="attention-row"><span className="attention-icon"><Icon name="warning"/></span><div><strong>{label(job.kind)}</strong><p>{job.error_message || job.error_code || '작업 상세에서 다음 단계를 확인하세요.'}</p></div><Badge value={job.state}/><Icon name="arrow" size={16}/></Link>)}</div> : <Empty icon="check" title="작업 목록에서 조치 대상을 찾지 못했습니다">전체 작업 상태와 이력은 작업 화면에서 확인할 수 있습니다.</Empty>}
    </Panel><Panel title="보관함으로 이어보기" subtitle="방송 한 번의 모든 녹화 조각을 한곳에."><div className="library-callout"><div className="stack-visual" aria-hidden="true"><span/><span/><span><Icon name="library" size={34}/></span></div><h3>방송이 끝나도, 이어서.</h3><p>세션과 원본 파일, 검증 결과를 방송별로 확인할 수 있습니다.</p><Link to="/v2/broadcasts" className="button secondary">방송 보관함<Icon name="arrow" size={16}/></Link></div></Panel></div>
  </>;
}
