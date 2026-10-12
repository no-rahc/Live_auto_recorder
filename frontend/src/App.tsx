import { Component, useEffect, useState, type ErrorInfo, type FormEvent, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { BroadcastDetails, Broadcasts } from './Broadcasts';
import { Channels } from './Channels';
import { Dashboard } from './Dashboard';
import { Jobs } from './Jobs';
import { Settings } from './Settings';
import { Badge, ErrorNotice, Icon } from './components';
import { bytes, date } from './format';
import { Link, useRouter } from './router';
import { useApiQuery } from './query';
import type { SystemStatus } from './types';
const menu = [{ path: '/v2', label: '현황', icon: 'dashboard' }, { path: '/v2/broadcasts', label: '방송 보관함', icon: 'library' }, { path: '/v2/channels', label: '채널', icon: 'channels' }, { path: '/v2/jobs', label: '작업', icon: 'jobs' }, { path: '/v2/settings', label: '설정', icon: 'settings' }];
export function App() {
  const { path, navigate } = useRouter();
  const status = useApiQuery<SystemStatus>('/status');
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [online, setOnline] = useState(navigator.onLine);
  const [lastHealthyStorage, setLastHealthyStorage] = useState<string | number | null>(null);
  useEffect(() => { const update = () => setOnline(navigator.onLine); window.addEventListener('online', update); window.addEventListener('offline', update); return () => { window.removeEventListener('online', update); window.removeEventListener('offline', update); }; }, []);
  useEffect(() => { if (status.data && ['ok','healthy','ready'].includes(status.data.storage?.status || '')) setLastHealthyStorage(status.data.observed_at || null); }, [status.data]);
  useEffect(() => { document.title = `${menu.find(item => item.path === (path === '/' ? '/v2' : path))?.label || '방송 상세'} · Live Auto Recorder`; }, [path]);
  const active = (route: string) => route === '/v2' ? path === '/v2' || path === '/' : path === route || path.startsWith(route + '/');
  const storage = status.data?.storage;
  const storageError = storage && !['ok','healthy','ready','unknown'].includes(storage.status);
  const disconnected = !online || Boolean(status.error);
  const searchSubmit = (event: FormEvent) => { event.preventDefault(); navigate(`/v2/broadcasts${search ? '?query=' + encodeURIComponent(search) : ''}`); setSearch(''); };
  let screen: ReactNode;
  if (path === '/v2' || path === '/') screen = <Dashboard status={status.data}/>;
  else if (path === '/v2/broadcasts') screen = <Broadcasts/>;
  else if (path.startsWith('/v2/broadcasts/')) { let id = path.slice('/v2/broadcasts/'.length); try { id = decodeURIComponent(id); } catch { /* Invalid percent escapes remain an opaque ID. */ } screen = <BroadcastDetails key={id} id={id}/>; }
  else if (path === '/v2/channels') screen = <Channels/>;
  else if (path === '/v2/jobs') screen = <Jobs/>;
  else if (path === '/v2/settings') screen = <Settings/>;
  else screen = <div className="panel empty"><h1>페이지를 찾을 수 없습니다</h1><Link to="/v2" className="button primary">현황으로 이동</Link></div>;
  return <><a href="#main-content" className="skip-link">본문으로 이동</a><div className="app-layout"><aside className="sidebar"><Link to="/v2" className="brand"><span className="brand-symbol"><i/><i/><i/></span><span>LIVE AUTO<br/><strong>RECORDER</strong></span><span className="brand-version">2</span></Link><div className="sidebar-label">WORKSPACE</div><nav aria-label="주 메뉴">{menu.map(item => <Link key={item.path} to={item.path} className={`nav-link ${active(item.path) ? 'active' : ''}`} aria-current={active(item.path) ? 'page' : undefined}><Icon name={item.icon}/><span>{item.label}</span>{item.icon === 'jobs' && Boolean(status.data && status.data.jobs.failed + status.data.jobs.blocked) && <span className="nav-count">{(status.data?.jobs.failed || 0) + (status.data?.jobs.blocked || 0)}</span>}</Link>)}</nav><div className="sidebar-bottom"><div className="local-note"><span className="local-dot"/><div><strong>나의 녹화 공간</strong><span>개인용 · 로컬 환경</span></div></div><a href="/legacy" className="legacy-link">기존 화면으로 이동<Icon name="external" size={14}/></a><span className="sidebar-version">Live Auto Recorder · {status.data?.version || '2.0'}</span></div></aside>
    <div className="workspace"><header className="topbar"><div className="mobile-brand"><span className="brand-symbol"><i/><i/><i/></span><strong>RECORDER <span>2.0</span></strong></div><form className="global-search" onSubmit={searchSubmit}><label htmlFor="global-search" className="sr-only">방송 보관함 검색</label><Icon name="search" size={18}/><input id="global-search" type="search" placeholder="보관함에서 방송 찾기" value={search} onChange={e => setSearch(e.target.value)}/></form><div className="topbar-status"><Badge value={disconnected ? 'error' : status.isPending ? 'pending' : 'ok'}>{disconnected ? '연결 끊김' : status.isPending ? '연결 확인 중' : '서버 연결됨'}</Badge><span className="storage-chip"><Icon name="storage" size={17}/>{storage?.free_bytes != null ? `${bytes(storage.free_bytes)} 여유` : storage ? `저장소 ${storage.status === 'ok' || storage.status === 'healthy' ? '정상' : storage.status === 'unknown' ? '미확인' : '확인 필요'}` : '저장소 확인 중'}</span><button type="button" className="icon-button refresh-button" aria-label="모든 상태 새로고침" disabled={status.isFetching} onClick={() => void queryClient.invalidateQueries({ queryKey: ['v2'] })}><Icon name="refresh" size={18}/></button><Link to="/v2/settings" className="icon-button mobile-settings" aria-label="설정"><Icon name="settings"/></Link></div></header>
    <main id="main-content" tabIndex={-1}><div className="global-notices">{!online && <div className="notice error" role="alert"><Icon name="warning"/><div><strong>갱신 중단 · 네트워크 연결을 확인하세요.</strong><p>마지막으로 확인한 데이터가 남아 있을 수 있습니다. 명령 완료 여부는 서버 연결 후 다시 확인합니다.</p></div></div>}<ErrorNotice error={status.error} stale={Boolean(status.data)} onRetry={() => void status.refetch()}/>{storageError && <div className="notice error" role="alert"><Icon name="storage"/><div><strong>저장소 확인이 필요합니다 · {storage.status}</strong><p>{storage.message || '저장소에 안전하게 기록할 수 있는지 확인하세요.'}</p><small>마지막 정상 확인 {date(storage.last_ok_at || lastHealthyStorage)}</small></div><Link to="/v2/settings" className="button secondary">저장소 설정</Link></div>}{status.data?.features?.durable_jobs !== false && status.data?.worker?.ready === false && <div className="notice warning" role="status"><Icon name="warning"/><div><strong>작업 실행기가 준비되지 않았습니다.</strong><p>접수된 작업이 바로 실행되지 않을 수 있습니다. 작업 상태와 서버 로그를 확인하세요.</p></div></div>}</div><ScreenBoundary key={path}>{screen}</ScreenBoundary><footer className="page-footer"><span>방송은 이어지고, 기록은 남습니다.</span><span>시간은 기기 시간대 기준</span></footer></main></div></div>
    <nav className="mobile-nav" aria-label="모바일 주 메뉴">{menu.slice(0, 4).map(item => <Link key={item.path} to={item.path} className={active(item.path) ? 'active' : ''} aria-current={active(item.path) ? 'page' : undefined}><Icon name={item.icon}/><span>{item.icon === 'library' ? '보관함' : item.label}</span></Link>)}</nav></>;
}
class ScreenBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(_error: Error, _info: ErrorInfo) { /* Do not emit sensitive API data into browser logs. */ }
  render() { return this.state.failed ? <div className="notice error" role="alert"><Icon name="warning"/><div><strong>화면을 표시하지 못했습니다.</strong><p>서버 응답을 확인하거나 화면을 다시 불러오세요.</p><button className="button secondary" onClick={() => window.location.reload()}>다시 불러오기</button></div></div> : this.props.children; }
}
