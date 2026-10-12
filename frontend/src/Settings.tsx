import { Badge, ErrorNotice, Icon, LastUpdated, Loading, PageHeading, Panel } from './components';
import { safeLegacyLink } from './format';
import { useApiQuery } from './query';
import type { Settings as SettingsType } from './types';

export function Settings() {
  const query = useApiQuery<SettingsType>('/settings');
  const settings = query.data;
  const config = safeLegacyLink(settings?.links?.configuration, '/config');
  const operations = safeLegacyLink(settings?.links?.operations, '/operations');
  return <><PageHeading eyebrow="SETTINGS" title="설정" description="녹화 환경과 데이터 보호 설정을 확인합니다." action={<span className="version-pill">{settings?.version || '2.0'}</span>}/>
    <ErrorNotice error={query.error} stale={Boolean(settings)} onRetry={() => void query.refetch()}/>{query.isPending ? <Loading/> : settings ? <>
    <div className="notice info"><Icon name="settings"/><div><strong>운영 상태는 새 화면에서, 상세 변경은 기존 설정에서.</strong><p>녹화 품질·알림·백업의 기존 설정을 유지합니다. 쿠키와 토큰 같은 비밀값은 여기에서 반환하거나 표시하지 않습니다.</p></div></div>
    <div className="settings-grid"><Panel title="저장소" subtitle="영상 경로와 데이터베이스를 분리해서 관리합니다."><dl className="definition-list"><div><dt>데이터베이스</dt><dd>{settings.storage?.database || '정보 확인 대기'}</dd></div><div><dt>녹화 영상</dt><dd>{settings.storage?.recordings || '기존 경로 사용'}</dd></div><div><dt>원본 파일 보존</dt><dd><Badge value={settings.storage?.originals_preserved ? 'ok' : 'unknown'}>{settings.storage?.originals_preserved ? '항상 보존' : '미확인'}</Badge></dd></div></dl><p className="section-note">SQLite 데이터는 로컬 영속 볼륨에 두고 영상은 기존 NAS 경로를 사용할 수 있습니다.</p><a className="settings-link" href={safeLegacyLink(settings.links?.files, '/files')}>파일과 저장 경로 확인<Icon name="external" size={16}/></a></Panel>
    <Panel title="녹화 정책" subtitle="채널별 자동 녹화와 미디어 출력 설정."><p className="settings-copy">{(settings.features?.channel_controls === false || settings.features?.durable_jobs === false) ? <>자동 녹화 설정은 <a href="/channels" className="text-link">채널 설정</a>에서 변경할 수 있습니다.</> : '자동 녹화 의도는 채널 화면에서 바꿀 수 있습니다.'} 품질, 출력 형식, 플러그인과 전역 녹화 옵션은 기존 설정을 사용합니다.</p><a className="settings-link" href={config}>녹화 설정 열기<Icon name="external" size={16}/></a></Panel>
    <Panel title="알림" subtitle="기존 알림 연결과 전달 설정을 유지합니다."><p className="settings-copy">알림 대상과 전송 결과는 운영 도구에서 관리합니다. 외부 전달은 재시도에 따라 중복될 수 있으므로 이력을 함께 확인하세요.</p><a className="settings-link" href={operations}>알림 운영 도구<Icon name="external" size={16}/></a></Panel>
    <Panel title="백업과 복원" subtitle="변경 전에는 복구 가능한 백업을 확인하세요."><p className="settings-copy">일반 백업은 비밀값을 제외합니다. 복원은 대상과 영향을 확인한 뒤 기존 보호 절차를 통해 진행합니다. 화면 전환만으로 데이터베이스를 이전 버전으로 되돌릴 수는 없습니다.</p><a className="settings-link" href={operations}>백업·복원 도구 열기<Icon name="external" size={16}/></a></Panel>
    <Panel title="고급" subtitle="점진 전환과 호환 도구."><dl className="definition-list"><div><dt>영속 작업 큐</dt><dd><Badge value={settings.features?.durable_jobs ? 'ok' : 'unknown'}>{settings.features?.durable_jobs ? '사용 중' : settings.features?.durable_jobs === false ? '사용 안 함' : '미확인'}</Badge></dd></div><div><dt>기존 화면</dt><dd>{settings.features?.legacy_ui ? '사용 가능' : '미확인'}</dd></div></dl><a className="settings-link" href="/legacy">기존 녹화 화면으로 이동<Icon name="external" size={16}/></a><a className="settings-link" href="/cookies">인증 설정 열기<Icon name="external" size={16}/></a></Panel></div>
    <LastUpdated at={query.dataUpdatedAt ? new Date(query.dataUpdatedAt).toISOString() : null} fetching={query.isFetching}/>
    </> : null}</>;
}
