import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useAction } from '../src/query';

function Harness() {
  const action = useAction<{ state: string }>();
  return <><button disabled={action.pending} onClick={() => void action.run('/jobs',{kind:'verify',target_id:'a',input_revision:1,options:{}})}>Request</button><span>{action.pending ? 'pending' : action.result?.state || action.error?.code || 'idle'}</span></>;
}
function mount() { render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><Harness/></QueryClientProvider>); }
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
it('does not mark a command complete or allow a second click before its response', async () => {
  let finish!: (response: Response) => void;
  const fetch = vi.fn(() => new Promise<Response>(resolve => {finish=resolve;})); vi.stubGlobal('fetch',fetch); mount();
  fireEvent.click(screen.getByText('Request')); fireEvent.click(screen.getByText('Request'));
  expect(fetch).toHaveBeenCalledTimes(1); expect(screen.getByText('pending')).toBeTruthy();
  finish(new Response(JSON.stringify({state:'queued'})));
  await waitFor(() => expect(screen.getByText('queued')).toBeTruthy());
  expect(screen.queryByText('succeeded')).toBeNull();
});
it('reuses the idempotency key after an ambiguous network failure', async () => {
  const fetch = vi.fn().mockRejectedValueOnce(new TypeError('lost')).mockResolvedValueOnce(new Response(JSON.stringify({state:'queued'})));
  vi.stubGlobal('fetch',fetch); mount(); fireEvent.click(screen.getByText('Request'));
  await waitFor(() => expect(screen.getByText('CONNECTION_LOST')).toBeTruthy());
  fireEvent.click(screen.getByText('Request')); await waitFor(() => expect(screen.getByText('queued')).toBeTruthy());
  expect(fetch.mock.calls[0][1].headers['Idempotency-Key']).toBe(fetch.mock.calls[1][1].headers['Idempotency-Key']);
});
