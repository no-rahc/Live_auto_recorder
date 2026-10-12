import { useState } from 'react';
import { Badge, Empty, ErrorNotice, Icon, LastUpdated, Loading, Modal, PageHeading, Pagination, Panel } from './components';
import { date, label } from './format';
import { useAction, useApiQuery } from './query';
import { useFilters, useRouter } from './router';
import type { Job, JobDetail, Page } from './types';

export function Jobs() {
  const { search, update } = useFilters();
  const { path, navigate } = useRouter();
  const params = new URLSearchParams(search); params.delete('selected'); params.set('limit', '50');
  const query = useApiQuery<Page<Job>>(`/jobs?${params}`);
  const selected = search.get('selected');
  const select = (id: string | null) => { const next = new URLSearchParams(search); if (id) next.set('selected', id); else next.delete('selected'); navigate(`${path}${next.size ? '?' + next : ''}`); };
  if (query.data?.available === false) return <>
    <PageHeading eyebrow="JOB QUEUE" title="작업" description="영속 작업 큐를 사용하지 않는 모드입니다."/>
    <ErrorNotice error={query.error} stale onRetry={() => void query.refetch()}/>
    <div className="panel"><Empty icon="jobs" title="파일 작업 기능이 꺼져 있습니다" action={<a href="/files" className="button secondary">기존 파일 탐색<Icon name="external" size={16}/></a>}>방송과 파일 이력은 볼 수 있지만, 검증·합치기·복구 작업은 이 모드에서 요청할 수 없습니다.</Empty><LastUpdated at={query.data.observed_at} fetching={query.isFetching}/></div>
  </>;
  return <><PageHeading eyebrow="JOB QUEUE" title="작업" description="접수부터 실제 완료까지, 작업의 모든 시도를 확인합니다."/>
    <div className="jobs-toolbar"><div className="filter-tabs" aria-label="작업 상태 필터">{[['','전체'],['queued','대기'],['running','실행 중'],['blocked','보류'],['failed','실패'],['retry_wait','재시도 대기'],['cancel_requested','취소 요청 중']].map(([value, title]) => <button type="button" key={value} className={(search.get('state') || '') === value ? 'active' : ''} onClick={() => update('state', value)} aria-pressed={(search.get('state') || '') === value}>{title}</button>)}</div><label className="filter-field"><span>작업 종류</span><select value={search.get('kind') || ''} onChange={e => update('kind', e.target.value)}><option value="">모든 작업</option><option value="verify">파일 검증</option><option value="merge">합치기</option><option value="recover">복구</option><option value="archive">보관</option></select></label></div>
    <ErrorNotice error={query.error} stale={Boolean(query.data)} onRetry={() => void query.refetch()}/>
    <div className="panel"><div className="list-caption"><strong>작업 목록</strong><span>접수된 작업은 서버에 보관됩니다</span></div>{query.isPending ? <Loading/> : query.data?.items.length ? <div className="jobs-list">{query.data.items.map(job => <button type="button" key={job.id} className="job-row" onClick={() => select(job.id)}><span className={`job-kind ${job.state === 'failed' ? 'bad' : ''}`}><Icon name={job.kind === 'verify' ? 'check' : job.kind === 'merge' ? 'library' : 'jobs'} size={22}/></span><div className="job-main"><strong>{label(job.kind)}</strong><span className="job-target">{job.target_id}</span><small>{job.error_code ? `${job.error_code} · ` : ''}{job.error_message || `접수 ${date(job.created_at, true)}`}</small></div><div className="job-progress"><Progress job={job}/><span>{job.attempts ?? 0} / {job.max_attempts ?? '—'}회 시도</span></div><div className="job-state"><Badge value={job.state}/>{job.next_run_at && <small>다음 시도 {date(job.next_run_at, true)}</small>}</div><Icon name="arrow" size={16}/></button>)}</div> : <Empty icon="jobs" title="조건에 맞는 작업이 없습니다">방송 상세에서 검증·합치기·복구 작업을 요청할 수 있습니다.</Empty>}<LastUpdated at={query.data?.observed_at} fetching={query.isFetching}/></div><Pagination nextCursor={query.data?.next_cursor}/>
    {selected && query.data && <JobDetailPanel id={selected} close={() => select(null)}/>}
  </>;
}
export function Progress({ job }: { job: Job }) {
  const raw = job.progress;
  const percent = typeof raw === 'number' ? raw : raw && typeof raw === 'object' && typeof raw.percent === 'number' ? raw.percent : null;
  const stage = typeof raw === 'string' ? raw : raw && typeof raw === 'object' && typeof raw.stage === 'string' ? raw.stage : null;
  return <div className="progress-content">{stage && <small>{stage}</small>}{percent != null ? <><progress max={100} value={Math.max(0, Math.min(100, percent))} aria-label="작업 진행률"/><small>{Math.round(percent)}%</small></> : <small>{job.state === 'running' ? '실행 결과 확인 중' : job.state === 'cancel_requested' ? '프로세스 종료 확인 중' : label(job.state)}</small>}</div>;
}
function JobDetailPanel({ id, close }: { id: string; close: () => void }) {
  const query = useApiQuery<JobDetail>(`/jobs/${encodeURIComponent(id)}`);
  const action = useAction<Job>();
  const [confirm, setConfirm] = useState<'cancel' | 'retry' | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const job = query.data;
  const execute = async () => {
    if (!confirm) return;
    const kind = confirm;
    const result = await action.run(`/jobs/${encodeURIComponent(id)}/${kind}`, {}, 'POST', false);
    if (result) { setNotice(kind === 'cancel' ? '취소 요청을 접수했습니다. 실제 종료 상태를 아래에서 확인하세요.' : '재시도 요청을 접수했습니다. 다음 시도 결과를 기다립니다.'); setConfirm(null); }
  };
  return <Modal title="작업 상세" close={() => { if (!action.pending) close(); }}><ErrorNotice error={query.error} stale={Boolean(job)} onRetry={() => void query.refetch()}/>{query.isPending ? <Loading/> : job ? <>
    <div className="job-detail-title"><h3>{label(job.kind)}</h3><Badge value={job.state}/></div><dl className="definition-list"><div><dt>작업 ID</dt><dd className="break-text">{job.id}</dd></div><div><dt>대상 ID</dt><dd className="break-text">{job.target_id}</dd></div><div><dt>접수 시각</dt><dd>{date(job.created_at)}</dd></div><div><dt>시도</dt><dd>{job.attempts ?? 0} / {job.max_attempts ?? '—'}</dd></div>{job.next_run_at && <div><dt>다음 재시도</dt><dd>{date(job.next_run_at)}</dd></div>}</dl>
    <div className="job-detail-progress"><Progress job={job}/></div>
    {(job.error_code || job.error_message) && <div className="notice error"><Icon name="warning"/><div><strong>{job.error_code || '작업 오류'}</strong><p>{job.error_message || '서버에서 상세 오류 메시지를 제공하지 않았습니다.'}</p><p>{remedy(job.error_code)}</p></div></div>}
    {job.state === 'cancel_requested' && <div className="notice info"><Icon name="clock"/><div><strong>취소를 요청했습니다.</strong><p>프로세스가 종료되었는지 확인 중입니다. 아직 취소 완료 상태가 아닙니다.</p></div></div>}
    {notice && <p className="inline-success" role="status">{notice}</p>}
    <ErrorNotice error={action.error}/>
    <Panel title="시도 이력">{job.attempt_history?.length ? <ol className="attempt-list">{job.attempt_history.map(attempt => <li key={attempt.id}><div><strong>{attempt.attempt_no}번째 시도</strong><Badge value={attempt.outcome || 'running'}/></div><p>{date(attempt.started_at, true)} → {attempt.ended_at ? date(attempt.ended_at, true) : '종료 확인 대기'}</p>{attempt.stage && <small>단계 · {attempt.stage}</small>}{attempt.exit_code != null && <small>종료 코드 · {attempt.exit_code}</small>}{attempt.error_code && <p className="error-text">{attempt.error_code}: {attempt.error_message || attempt.error_detail}</p>}</li>)}</ol> : <p className="section-note">아직 실행된 시도가 없습니다.</p>}</Panel>
    {job.log && <details className="log-details"><summary>작업 로그</summary><pre tabIndex={0}>{job.log}</pre></details>}
    {confirm ? <div className="confirm-inline"><strong>{confirm === 'cancel' ? '이 작업의 취소를 요청할까요?' : '이 작업을 다시 시도할까요?'}</strong><p>{confirm === 'cancel' ? '진행 중인 프로세스가 있으면 종료 확인 후 취소됩니다. 원본과 이미 발행된 결과는 보존됩니다.' : '오류 원인을 해결했는지 확인하세요. 기존 작업 ID와 시도 이력을 유지하며 새 시도를 만듭니다.'}</p><div className="modal-actions"><button type="button" className="button secondary" disabled={action.pending} onClick={() => setConfirm(null)}>돌아가기</button><button type="button" className="button primary" disabled={action.pending} onClick={() => void execute()}>{action.pending ? '요청 중…' : confirm === 'cancel' ? '취소 요청' : '재시도 요청'}</button></div></div>
      : <div className="modal-actions"><button type="button" className="button secondary" onClick={close}>닫기</button>{['failed','blocked','cancelled','interrupted'].includes(job.state) && <button type="button" className="button primary" onClick={() => { action.clear(); setConfirm('retry'); }}><Icon name="refresh" size={16}/>재시도</button>}{['queued','running','retry_wait','blocked'].includes(job.state) && <button type="button" className="button danger-outline" onClick={() => { action.clear(); setConfirm('cancel'); }}>작업 취소</button>}</div>}
    <LastUpdated at={job.observed_at} fetching={query.isFetching}/>
  </> : null}</Modal>;
}
function remedy(code?: string | null): string {
  if (!code) return '대상 파일과 서버 상태를 확인한 후 다시 시도하세요.';
  if (/STORAGE|DISK|SPACE|MOUNT/.test(code)) return '저장소 연결, 마운트와 여유 공간을 확인한 후 재시도하세요.';
  if (/INPUT|FILE|PATH/.test(code)) return '입력 파일이 존재하며 변경되지 않았는지 확인하세요. 원본 경로를 확인한 뒤 새 작업이 필요할 수 있습니다.';
  if (/LEASE|PROCESS|OWNER/.test(code)) return '기존 프로세스가 종료되었는지 확인해야 합니다. 소유권이 불확실하면 강제로 재실행하지 마세요.';
  if (/AUTH|COOKIE|TOKEN/.test(code)) return '기존 인증 설정 화면에서 연결 상태를 확인하세요. 비밀값은 이 화면에 표시하지 않습니다.';
  return '오류 메시지와 시도 이력을 확인하고 원인을 해결한 뒤 다시 시도하세요.';
}
