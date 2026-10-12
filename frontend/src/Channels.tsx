import { useState } from 'react';
import { Badge, Empty, ErrorNotice, Icon, LastUpdated, Loading, Modal, PageHeading } from './components';
import { date, label } from './format';
import { useAction, useApiQuery, useCommand, useChannelsQuery } from './query';
import type { Channel, Command, Page } from './types';

export function Channels() {
  const query = useChannelsQuery();
  return <><PageHeading eyebrow="CHANNELS" title="채널" description="자동 녹화 설정과 실제 녹화 상태를 따로 확인하세요." action={<a href="/channels" className="button primary"><Icon name="plus"/>채널 추가 · 편집<Icon name="external" size={16}/></a>}/>
    <div className="notice info"><Icon name="channels"/><div><strong>자동 녹화를 꺼도 현재 방송은 계속 녹화됩니다.</strong><p>이번 방송을 끝내려면 ‘이번 방송 중지’를 사용하세요. 한 번 녹화는 기존 자동 녹화 설정을 바꾸지 않습니다.</p></div></div>
    <ErrorNotice error={query.error} stale={Boolean(query.data)} onRetry={() => void query.refetch()}/>
    {query.isPending ? <Loading/> : query.data?.items.length ? <div className="channel-grid">{query.data.items.map(channel => <ChannelCard key={channel.id} channel={channel}/>)}</div> : <div className="panel"><Empty icon="channels" title="첫 번째 채널을 추가하세요" action={<a href="/channels" className="button primary"><Icon name="plus"/>채널 추가</a>}>기존 채널 설정 화면에서 CHZZK 또는 YouTube 채널을 등록할 수 있습니다.</Empty></div>}
    <LastUpdated at={query.data?.observed_at} fetching={query.isFetching}/>
    <p className="compat-note">채널 등록과 품질·경로 편집은 기존 설정 화면에서 제공합니다.</p>
  </>;
}
function ChannelCard({ channel }: { channel: Channel }) {
  const mode = useAction<Channel>();
  const action = useAction<Command>();
  const [receipt, setReceipt] = useState<Command | null>(null);
  const [confirm, setConfirm] = useState<'start_once' | 'stop_current' | null>(null);
  const { command, state, settled, error: commandError } = useCommand(receipt);
  const active = ['recording','starting','reconnecting','stopping'].includes(channel.actual_state);
  const pending = action.pending || Boolean(receipt && !settled && !active);
  const issueCommand = async () => {
    if (!confirm) return;
    const response = await action.run(`/channels/${encodeURIComponent(channel.id)}/commands`, { kind: confirm, ...(confirm === 'stop_current' ? { broadcast_id: channel.broadcast_id } : {}) });
    if (response) { setReceipt(response); setConfirm(null); }
  };
  return <article className="channel-card"><div className="card-top"><span className={`platform-mark ${channel.platform}`}>{label(channel.platform)}</span><span className="small-label">REV {channel.revision}</span></div>
    <div className="channel-identity"><span className="channel-avatar">{channel.name.slice(0, 1).toLocaleUpperCase()}</span><div><h2>{channel.name}</h2><p className="channel-id">{channel.id}</p></div></div>
    <div className="channel-states"><div><span>자동 녹화</span><strong className={channel.desired_mode === 'auto' ? 'green-text' : ''}>{channel.desired_mode === 'auto' ? '켜짐' : '꺼짐'}</strong></div><div><span>실제 상태</span><Badge value={channel.actual_state}/></div></div>
    {channel.reason_code && <p className="reason-code">상태 사유 · {channel.reason_code}</p>}
    <small className="muted">마지막 관측 {date(channel.observed_at, true)}</small>
    <ErrorNotice error={mode.error}/><ErrorNotice error={action.error}/><ErrorNotice error={commandError}/>
    {mode.result && !mode.pending && <p className="inline-success" role="status">자동 녹화 설정을 저장했습니다. 실제 상태는 관측 결과로 갱신됩니다.</p>}
    {receipt && <div className={`command-status ${state === 'failed' ? 'error-text' : ''}`} role="status"><Icon name={settled ? 'check' : 'clock'} size={16}/><span>{settled ? ['failed', 'rejected', 'blocked', 'interrupted'].includes(state) ? '명령 처리 실패 · 상태와 오류를 확인하세요.' : '명령 처리가 끝났습니다. 실제 상태를 확인하세요.' : '명령 접수 · 실제 처리 결과를 기다리는 중입니다.'}</span></div>}
    {command?.error_code && <p className="reason-code">명령 오류 · {command.error_code}{command.error_message ? `: ${command.error_message}` : ""}</p>}
    <div className="channel-actions"><button type="button" className="button secondary" disabled={mode.pending || pending} onClick={() => void mode.run(`/channels/${encodeURIComponent(channel.id)}`, { desired_mode: channel.desired_mode === 'auto' ? 'paused' : 'auto', expected_revision: channel.revision }, 'PATCH', false)}>{mode.pending ? '설정 저장 중…' : channel.desired_mode === 'auto' ? '자동 녹화 끄기' : '자동 녹화 켜기'}</button>
      {active ? <button type="button" className="button danger-outline" disabled={pending || !channel.broadcast_id || channel.actual_state === 'stopping'} title={!channel.broadcast_id ? '방송 ID를 확인한 후 중지할 수 있습니다.' : undefined} onClick={() => { action.clear(); setConfirm('stop_current'); }}><Icon name="stop" size={16}/>{channel.actual_state === 'stopping' ? '중지 확인 중' : '이번 방송 중지'}</button>
        : <button type="button" className="button primary" disabled={pending || mode.pending} onClick={() => { action.clear(); setConfirm('start_once'); }}><Icon name="play" size={16}/>{pending ? '명령 처리 중…' : '지금 한 번 녹화'}</button>}
    </div>
    {confirm && <Modal title={confirm === 'stop_current' ? '이번 방송을 중지할까요?' : '지금 한 번 녹화할까요?'} close={() => { if (!action.pending) setConfirm(null); }}><p><strong>{channel.name}</strong></p><p>{confirm === 'stop_current' ? '진행 중인 녹화 프로세스의 종료를 요청합니다. 저장된 원본은 유지되며 같은 방송은 자동으로 다시 시작하지 않습니다.' : '이 채널에 한 번 녹화를 요청합니다. 방송 상태를 확인한 뒤 시작하며, 기존 자동 녹화 설정은 유지됩니다.'}</p>{confirm === 'stop_current' && <p className="path-box">대상 방송: {channel.broadcast_id}</p>}<ErrorNotice error={action.error}/><div className="modal-actions"><button type="button" className="button secondary" disabled={action.pending} onClick={() => setConfirm(null)}>돌아가기</button><button type="button" className={`button ${confirm === 'stop_current' ? 'danger' : 'primary'}`} disabled={action.pending} onClick={() => void issueCommand()}>{action.pending ? '명령 전송 중…' : confirm === 'stop_current' ? '중지 요청' : '한 번 녹화 요청'}</button></div></Modal>}
  </article>;
}
