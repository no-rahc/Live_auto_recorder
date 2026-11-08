import { useQueryClient } from '@tanstack/react-query';
import { Component, useEffect, type ErrorInfo, type ReactNode } from 'react';
import { Broadcasts, BroadcastDetails } from './Broadcasts';
import { Jobs } from './Jobs';
import { Icon } from './components';
import { useRouter } from './router';

/** Feature island inside the existing console. The v1 shell owns navigation. */
export function App() {
  const { path } = useRouter();
  const client = useQueryClient();
  const isJobs = path === '/jobs';
  useEffect(() => {
    const section = isJobs ? '/jobs' : '/broadcasts';
    document.querySelectorAll('#mySidenav a[href]').forEach(link => {
      const active = link.getAttribute('href') === section;
      link.classList.toggle('lar-active', active);
      if (active) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
    });
    const label = isJobs ? '작업 상태' : '방송 보관함';
    document.title = label + ' · Live Auto Recorder';
    const heading = document.querySelector('.lar-topbar-context strong');
    if (heading) heading.textContent = label;
    const icon = document.querySelector('.lar-topbar-context-icon');
    const currentIcon = document.querySelector(`#mySidenav a[href="${section}"] .lar-sidebar-link-icon svg`);
    if (icon && currentIcon) icon.replaceChildren(currentIcon.cloneNode(true));
  }, [path, isJobs]);
  let screen: ReactNode;
  if (isJobs) screen = <Jobs/>;
  else if (path === '/broadcasts') screen = <Broadcasts/>;
  else if (path.startsWith('/broadcasts/')) {
    let id = '';
    try { id = decodeURIComponent(path.slice('/broadcasts/'.length)); } catch { /* Render a safe fallback. */ }
    screen = id ? <BroadcastDetails id={id}/> : <UnknownPage/>;
  } else screen = <UnknownPage/>;
  return <><div className="library-tools"><button type="button" className="button secondary" aria-label="모든 상태 새로고침" onClick={() => void client.invalidateQueries({ queryKey: ['v2'] })}><Icon name="refresh" size={14}/>새로고침</button></div><ScreenBoundary key={path}>{screen}</ScreenBoundary></>;
}
function UnknownPage() { return <div className="notice error"><Icon name="warning"/><div><strong>화면을 찾을 수 없습니다.</strong><p><a href="/broadcasts">방송 보관함으로 돌아가기</a></p></div></div>; }
class ScreenBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(_error: Error, _info: ErrorInfo) { /* Never log sensitive response data. */ }
  render() { return this.state.failed ? <div className="notice error" role="alert"><Icon name="warning"/><div><strong>화면을 표시하지 못했습니다.</strong><p>서버 응답을 확인하거나 화면을 다시 불러오세요.</p><button className="button secondary" onClick={() => window.location.reload()}>다시 불러오기</button></div></div> : this.props.children; }
}
