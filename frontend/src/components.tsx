import { useEffect, useRef, type ReactNode } from 'react';
import type { ApiError } from './api';
import { date, label } from './format';
import { Link, useRouter } from './router';

const iconPaths: Record<string, ReactNode> = {
  dashboard: <><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></>,
  library: <><rect x="4" y="6" width="16" height="15" rx="2"/><path d="M8 3h8M9 11l6 3-6 3z"/></>,
  channels: <><circle cx="12" cy="12" r="2"/><path d="M7 7a7 7 0 000 10m10-10a7 7 0 010 10M4 4a11 11 0 000 16M20 4a11 11 0 010 16"/></>,
  jobs: <><rect x="5" y="5" width="14" height="16" rx="2"/><path d="M9 3h6v4H9zM9 12h6M9 16h4"/></>,
  settings: <><path d="M9 3l-1 3-3 1-2 4 2 3 1 4 4 2 3-1 4 1 3-4-1-3 1-4-4-2-2-3z"/><circle cx="12" cy="12" r="3"/></>,
  arrow: <path d="M5 12h14m-5-5l5 5-5 5"/>, back: <path d="M19 12H5m5-5l-5 5 5 5"/>,
  search: <><circle cx="10.5" cy="10.5" r="6.5"/><path d="M16 16l5 5"/></>,
  plus: <path d="M12 5v14M5 12h14"/>, refresh: <><path d="M20 7v5h-5M4 17v-5h5M6 7a7 7 0 0113 3M5 14a7 7 0 0013 3"/></>,
  storage: <><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M3 14h18M7 17h.01M11 17h.01"/></>,
  check: <path d="M5 12l4 4L19 6"/>, warning: <><path d="M10.3 4l-8 14A2 2 0 004 21h16a2 2 0 001.7-3l-8-14a2 2 0 00-3.4 0z"/><path d="M12 9v4m0 4h.01"/></>,
  clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
  close: <path d="M6 6l12 12M18 6L6 18"/>, external: <><path d="M14 3h7v7m0-7L11 13M10 3H5a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-5"/></>,
  file: <><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8zM14 2v6h6M8 13h8M8 17h5"/></>,
  play: <path d="M7 4l14 8-14 8z"/>, stop: <rect x="6" y="6" width="12" height="12" rx="1"/>,
};
export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{iconPaths[name] || iconPaths.file}</svg>;
}
export function Badge({ value, children }: { value?: string | null; children?: ReactNode }) {
  const kind = ['recording','running','watching','healthy','ok','succeeded','completed','passed','valid','verified'].includes(value || '') ? 'good'
    : ['failed','error','invalid','damaged'].includes(value || '') ? 'bad'
    : ['blocked','retry_wait','cancel_requested','stopping','starting','reconnecting','interrupted','pending'].includes(value || '') ? 'warn' : 'neutral';
  return <span className={`badge ${kind}`}><span className="badge-dot"/>{children || label(value)}</span>;
}
export function PageHeading({ eyebrow, title, description, action }: { eyebrow: string; title: string; description?: string; action?: ReactNode }) {
  return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1>{description && <p>{description}</p>}</div>{action && <div className="heading-action">{action}</div>}</div>;
}
export function Panel({ title, subtitle, action, children, className = '' }: { title: string; subtitle?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return <section className={`panel ${className}`}><div className="panel-heading"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>{action}</div>{children}</section>;
}
export function Empty({ icon = 'library', title, children, action }: { icon?: string; title: string; children: ReactNode; action?: ReactNode }) {
  return <div className="empty"><span className="empty-icon"><Icon name={icon} size={28}/></span><h3>{title}</h3><p>{children}</p>{action}</div>;
}
export function ErrorNotice({ error, onRetry, stale = false }: { error?: ApiError | Error | null; onRetry?: () => void; stale?: boolean }) {
  if (!error) return null;
  const apiError = error as ApiError;
  return <div className="notice error" role="alert"><Icon name="warning"/><div><strong>{apiError.status === 409 ? '다른 곳에서 상태가 바뀌었습니다' : stale ? '갱신 중단 · 마지막 확인 데이터' : '요청을 완료하지 못했습니다'}</strong><p>{error.message}</p>{apiError.status === 409 && <p>최신 상태를 다시 불러왔습니다. 내용을 확인한 뒤 다시 실행하세요.</p>}{apiError.status === 0 && <p>명령을 보냈다면 서버에서 처리 중일 수 있습니다. 완료 여부를 확인하기 전에는 완료로 표시하지 않습니다.</p>}<small>{apiError.code}{apiError.requestId ? ` · 요청 ${apiError.requestId}` : ''}</small></div>{onRetry && <button type="button" className="button secondary" onClick={onRetry}>다시 확인</button>}</div>;
}
export function Loading() { return <div className="loading" role="status"><span className="spinner"/>최근 상태를 불러오고 있습니다</div>; }
export function LastUpdated({ at, fetching = false }: { at?: string | number | null; fetching?: boolean }) {
  return <div className="updated"><Icon name={fetching ? 'refresh' : 'clock'} size={14}/>{fetching ? '갱신 중 · ' : '마지막 확인 · '}{date(at)}</div>;
}
export function Modal({ title, children, close }: { title: string; children: ReactNode; close: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { dialog.current?.showModal(); const element = dialog.current; return () => element?.close(); }, []);
  return <dialog className="modal" ref={dialog} aria-labelledby="modal-title" onCancel={event => { event.preventDefault(); close(); }} onClick={event => { if (event.target === event.currentTarget) close(); }}><div className="modal-body"><div className="modal-header"><h2 id="modal-title">{title}</h2><button type="button" className="icon-button" aria-label="닫기" onClick={close}><Icon name="close"/></button></div>{children}</div></dialog>;
}
export function Pagination({ nextCursor }: { nextCursor?: string | null }) {
  const { path, search, navigate } = useRouter();
  const move = (cursor: string | null) => { const next = new URLSearchParams(search); if (cursor) next.set('cursor', cursor); else next.delete('cursor'); navigate(`${path}${next.size ? '?' + next : ''}`); };
  if (!nextCursor && !search.has('cursor')) return null;
  return <div className="pagination">{search.has('cursor') && <button type="button" className="button secondary" onClick={() => move(null)}>처음으로</button>}{nextCursor && <button type="button" className="button secondary" onClick={() => move(nextCursor)}>다음 방송 / 작업<Icon name="arrow"/></button>}</div>;
}
export function DetailLink({ id, children = '상세 보기' }: { id: string; children?: ReactNode }) { return <Link to={`/v2/broadcasts/${encodeURIComponent(id)}`} className="text-link">{children}<Icon name="arrow" size={16}/></Link>; }
