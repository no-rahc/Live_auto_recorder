import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, allChannels, ApiError, latestRevision, pollingInterval } from '../src/api';
import { bytes, date, duration, elapsed, safeLegacyLink, validation } from '../src/format';

afterEach(() => vi.unstubAllGlobals());
describe('read contract and display', () => {
  it('formats Unix seconds and ISO timestamps as the same date', () => {
    expect(date(1791727200)).toBe(date('2026-10-11T14:00:00Z'));
    expect(date(1791727200000)).toBe(date('2026-10-11T14:00:00Z'));
    expect(date('bad time')).toBe('확인되지 않음');
    expect(elapsed('bad')).toBe('시간 미상');
  });
  it('keeps unknown metadata unknown and accepts zero measurements', () => {
    expect(bytes()).toBe('크기 미상'); expect(bytes(0)).toBe('0 B');
    expect(duration(0)).toBe('00:00:00'); expect(duration(3661)).toBe('01:01:01');
    expect(duration()).toBe('길이 미상'); expect(validation({status:'valid'})).toBe('valid');
  });
  it('rejects external settings links and scheme injection', () => {
    for (const unsafe of ['https://example.com','//example.com','javascript:alert(1)','/\\evil.com']) expect(safeLegacyLink(unsafe, '/config')).toBe('/config');
    expect(safeLegacyLink('/operations', '/config')).toBe('/operations');
  });
  it('ignores older entity revisions', () => {
    const current = { id: 'a', revision: 4, actual_state: 'recording' };
    expect(latestRevision(current, { ...current, revision: 3, actual_state: 'idle' })).toBe(current);
  });
  it('ignores late page observations, including deleted rows', () => {
    const current = { observed_at: 200, items: [{id:'a',revision:4}] };
    expect(latestRevision(current, {observed_at:100,items:[]})).toBe(current);
  });
  it('merges each list row by revision without reintroducing missing rows', () => {
    const current = {items:[{id:'a',revision:4},{id:'b',revision:1}]};
    expect(latestRevision(current, {items:[{id:'a',revision:3}]})).toEqual({items:[{id:'a',revision:4}]});
  });
  it('allows newer observation with non-monotonic hash revisions', () => {
    const current = {id:'b',revision:500,observed_at:100,title:'Old'};
    expect(latestRevision(current,{...current,revision:20,observed_at:200,title:'New'}).title).toBe('New');
  });
  it('slows polling in hidden tabs', () => {
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden'); expect(pollingInterval()).toBe(30000); vi.restoreAllMocks();
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible'); expect(pollingInterval()).toBe(5000); vi.restoreAllMocks();
  });
});
describe('API boundary', () => {
  it('uses same-origin JSON requests and passes cancellation signal', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({items:[]})));
    vi.stubGlobal('fetch',fetch); const controller = new AbortController();
    expect(await api('/channels', {signal:controller.signal})).toEqual({items:[]});
    expect(fetch).toHaveBeenCalledWith('/api/v2/channels', expect.objectContaining({credentials:'same-origin',signal:controller.signal}));
  });
  it('preserves error code, conflict status and request ID', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({code:'REVISION_CONFLICT',message:'changed',request_id:'r1'}),{status:409})));
    await expect(api('/channels')).rejects.toMatchObject({status:409,code:'REVISION_CONFLICT',requestId:'r1'});
  });
  it('does not convert an aborted query into a connection failure', async () => {
    vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new DOMException('aborted','AbortError')));
    await expect(api('/status')).rejects.toHaveProperty('name','AbortError');
  });
  it('marks network failure as ambiguous rather than completed', async () => {
    vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    await expect(api('/jobs',{method:'POST',body:'{}'})).rejects.toMatchObject({status:0,code:'CONNECTION_LOST',retryable:true});
  });
  it('normalizes non-JSON server errors without leaking HTML', async () => {
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('<html>private internal traceback</html>',{status:500})));
    try { await api('/status'); } catch(error) { expect(error).toBeInstanceOf(ApiError); expect((error as Error).message).not.toContain('traceback'); }
  });
});

it('loads every channel page for the shared dashboard and controls cache', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({items:[{id:'a',revision:1}],next_cursor:'50',observed_at:100})))
    .mockResolvedValueOnce(new Response(JSON.stringify({items:[{id:'b',revision:1}],next_cursor:null,observed_at:101})));
  vi.stubGlobal('fetch',fetch);
  expect((await allChannels()).items.map(item=>item.id)).toEqual(['a','b']);
  expect(fetch.mock.calls[1][0]).toBe('/api/v2/channels?cursor=50');
});
