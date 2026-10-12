import type { ApiErrorBody, Versioned, Channel, Page } from './types';

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryable: boolean;
  readonly requestId?: string;
  constructor(status: number, body: ApiErrorBody) {
    super(body.message); this.name = 'ApiError'; this.status = status;
    this.code = body.code; this.retryable = Boolean(body.retryable); this.requestId = body.request_id;
  }
}
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  return request<T>(`/api/v2${path}`, options);
}
async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, {
      ...options, credentials: 'same-origin',
      headers: { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers },
    });
  } catch (error) {
    if (error && typeof error === 'object' && 'name' in error && error.name === 'AbortError') throw error;
    throw new ApiError(0, { code: 'CONNECTION_LOST', message: '서버에 연결할 수 없습니다. 마지막으로 확인한 데이터를 표시합니다.', retryable: true });
  }
  let data: unknown;
  try { data = await response.json(); } catch { data = null; }
  if (!response.ok) {
    const outer = (data || {}) as Record<string, unknown>;
    const body = (outer.error || outer.detail || outer) as Partial<ApiErrorBody>;
    throw new ApiError(response.status, {
      code: typeof body.code === 'string' ? body.code : `HTTP_${response.status}`,
      message: typeof body.message === 'string' ? body.message : typeof outer.detail === 'string' ? outer.detail : '요청을 처리하지 못했습니다. 다시 확인해 주세요.',
      retryable: body.retryable, request_id: body.request_id,
    });
  }
  return data as T;
}

/** Compatibility actions use the running recorder, without durable-command semantics. */
export async function compatibilityRecording(channelId: string, action: 'start' | 'stop'): Promise<void> {
  const result = await request<{ status?: string; code?: string; message?: string } | null>(`/api/${action}_recording/${encodeURIComponent(channelId)}`, {
    method: 'POST', ...(action === 'start' ? { body: JSON.stringify({ is_user_request: true }) } : {}),
  });
  if (result?.status !== 'success') throw new ApiError(0, {
    code: result?.code || 'REQUEST_UNKNOWN',
    message: result?.message || '요청 결과를 확인하지 못했습니다. 채널의 실제 상태를 확인하세요.',
  });
}
export function commandKey(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  const random = crypto.getRandomValues(new Uint8Array(16));
  random[6] = (random[6] & 15) | 64; random[8] = (random[8] & 63) | 128;
  const hex = Array.from(random, byte => byte.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}

/** A late read must not replace a newer revision in the same query cache. */
export function latestRevision<T>(previous: T | undefined, next: T): T {
  if (!previous || !next || typeof next !== 'object') return next;
  const oldObserved = 'observed_at' in (previous as object) ? epoch((previous as { observed_at?: string | number }).observed_at) : 0;
  const newObserved = 'observed_at' in next ? epoch((next as { observed_at?: string | number }).observed_at) : 0;
  if (oldObserved && newObserved && oldObserved > newObserved) return previous;
  if ('items' in next && Array.isArray(next.items) && typeof previous === 'object' && 'items' in previous && Array.isArray(previous.items)) {
    const old = new Map(previous.items.map((item: Versioned) => [item.id, item]));
    return { ...next, items: next.items.map((item: Versioned) => latestRevision(old.get(item.id), item)) };
  }
  const before = previous as Partial<Versioned>;
  const after = next as Partial<Versioned>;
  if (before.id === after.id && typeof before.revision === 'number' && typeof after.revision === 'number' && before.revision > after.revision && !(newObserved > oldObserved)) return previous;
  return next;
}
export const pollingInterval = () => document.visibilityState === 'hidden' ? 30_000 : 5_000;

function epoch(value?: string | number): number { return typeof value === 'number' ? (Math.abs(value) < 100_000_000_000 ? value * 1000 : value) : value ? Date.parse(value) : 0; }

/** Channel lists are shared by dashboard, controls, and filters; include every page. */
export async function allChannels(signal?: AbortSignal): Promise<Page<Channel>> {
  const channels = new Map<string, Channel>();
  const seen = new Set<string>();
  let cursor: string | null | undefined;
  let observed_at: Page<Channel>['observed_at'];
  do {
    const page: Page<Channel> = await api(`/channels${cursor ? '?cursor=' + encodeURIComponent(cursor) : ''}`, { signal });
    for (const channel of page.items) channels.set(channel.id, channel);
    observed_at = page.observed_at;
    cursor = page.next_cursor;
    if (cursor && seen.has(cursor)) throw new ApiError(500, {code:'INVALID_CURSOR',message:'채널 목록의 다음 페이지를 확인하지 못했습니다.'});
    if (cursor) seen.add(cursor);
  } while (cursor);
  return { items: Array.from(channels.values()), next_cursor: null, observed_at };
}
