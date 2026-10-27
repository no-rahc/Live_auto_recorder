import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { api, allChannels, ApiError, commandKey, latestRevision, pollingInterval } from './api';
import type { Channel, Page } from './types';

export function useApiQuery<T>(path: string, enabled = true, loader?: (signal: AbortSignal) => Promise<T>) {
  return useQuery<T, ApiError>({ queryKey: ['v2', path], queryFn: ({ signal }) => loader ? loader(signal) : api<T>(path, { signal }), enabled,
    refetchInterval: pollingInterval, refetchIntervalInBackground: true, staleTime: 3000, retry: 1,
    structuralSharing: (old, next) => latestRevision(old as T | undefined, next as T) });
}

/** No optimistic updates. Keep the same key on an ambiguous transport failure. */
export function useAction<T = unknown>() {
  const queryClient = useQueryClient();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<T | null>(null);
  const inflight = useRef(false);
  const key = useRef<{ fingerprint: string; value: string } | null>(null);
  const run = async (path: string, body?: unknown, method = 'POST', idempotent = true): Promise<T | null> => {
    if (inflight.current) return null;
    inflight.current = true; setPending(true); setError(null); setResult(null);
    const fingerprint = `${method}:${path}:${JSON.stringify(body)}`;
    if (!key.current || key.current.fingerprint !== fingerprint) key.current = { fingerprint, value: commandKey() };
    try {
      const value = await api<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body), headers: idempotent ? { 'Idempotency-Key': key.current.value } : {} });
      setResult(value); key.current = null;
      await queryClient.invalidateQueries({ queryKey: ['v2'] });
      return value;
    } catch (cause) {
      const failure = cause instanceof ApiError ? cause : new ApiError(0, { code: 'REQUEST_UNKNOWN', message: '응답을 확인하지 못했습니다. 상태를 새로 확인한 후 다시 시도하세요.' });
      setError(failure);
      if (failure.status !== 0 && failure.status < 500) key.current = null;
      if (failure.status === 409) await queryClient.invalidateQueries({ queryKey: ['v2'] });
      return null;
    } finally { inflight.current = false; setPending(false); }
  };
  return { run, pending, error, result, clear: () => { setError(null); setResult(null); } };
}
export function useChannelsQuery() { return useApiQuery<Page<Channel>>('/channels', true, allChannels); }
