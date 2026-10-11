import { createContext, useContext, useEffect, useState, type MouseEvent, type ReactNode } from 'react';
interface RouterValue { path: string; search: URLSearchParams; navigate: (url: string, replace?: boolean) => void }
const Router = createContext<RouterValue | null>(null);
export function RouterProvider({ children }: { children: ReactNode }) {
  const [location, setLocation] = useState(() => window.location.pathname + window.location.search);
  useEffect(() => { const change = () => setLocation(window.location.pathname + window.location.search); window.addEventListener('popstate', change); return () => window.removeEventListener('popstate', change); }, []);
  const navigate = (url: string, replace = false) => {
    if (replace) window.history.replaceState(null, '', url); else window.history.pushState(null, '', url);
    setLocation(window.location.pathname + window.location.search);
  };
  const [path, query] = location.split('?');
  return <Router.Provider value={{ path: path.replace(/\/$/, '') || '/', search: new URLSearchParams(query || ''), navigate }}>{children}</Router.Provider>;
}
export function useRouter() { const value = useContext(Router); if (!value) throw new Error('Missing router'); return value; }
export function Link({ to, children, className = '', ...props }: { to: string; children: ReactNode; className?: string; 'aria-label'?: string; 'aria-current'?: 'page' | undefined }) {
  const { navigate } = useRouter();
  const click = (event: MouseEvent<HTMLAnchorElement>) => { if (event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) { event.preventDefault(); navigate(to); } };
  return <a href={to} onClick={click} className={className} {...props}>{children}</a>;
}
export function useFilters() {
  const { path, search, navigate } = useRouter();
  const update = (key: string, value: string) => { const next = new URLSearchParams(search); if (value) next.set(key, value); else next.delete(key); next.delete('cursor'); navigate(`${path}${next.size ? '?' + next.toString() : ''}`, true); };
  return { search, update };
}
