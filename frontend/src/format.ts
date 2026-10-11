export function date(value?: string | number | null, short = false): string {
  if (!value) return '확인되지 않음';
  const parsed = new Date(typeof value === "number" ? (Math.abs(value) < 100_000_000_000 ? value * 1000 : value) : value);
  if (Number.isNaN(parsed.getTime())) return '확인되지 않음';
  return new Intl.DateTimeFormat('ko-KR', short ? { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' } : { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(parsed);
}
export function bytes(value?: number | null): string {
  if (value == null || !Number.isFinite(value)) return '크기 미상';
  const units = ['B', 'KB', 'MB', 'GB', 'TB']; let i = 0; let size = Math.max(0, value);
  while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
  return `${new Intl.NumberFormat('ko-KR', { maximumFractionDigits: i > 0 ? 1 : 0 }).format(size)} ${units[i]}`;
}
export function duration(value?: number | null): string {
  if (value == null || !Number.isFinite(value)) return '길이 미상';
  const seconds = Math.max(0, Math.floor(value));
  return `${Math.floor(seconds / 3600).toString().padStart(2, '0')}:${Math.floor(seconds % 3600 / 60).toString().padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`;
}
export function elapsed(value?: string | number | null): string {
  if (!value) return '시간 미상';
  const epoch = typeof value === 'number' ? (Math.abs(value) < 100_000_000_000 ? value * 1000 : value) : Date.parse(value);
  if (Number.isNaN(epoch)) return '시간 미상';
  return duration((Date.now() - epoch) / 1000);
}
export const labels: Record<string, string> = {
  idle: '대기 중', watching: '감시 중', starting: '시작 중', recording: '녹화 중', reconnecting: '재연결 중', stopping: '중지 중',
  blocked: '보류', error: '오류', queued: '대기', running: '실행 중', retry_wait: '재시도 대기', failed: '실패',
  cancel_requested: '취소 요청 중', cancelled: '취소됨', succeeded: '완료', completed: '완료', ended: '종료됨',
  interrupted: '중단됨', pending: '확인 대기', unknown: '미확인', valid: '검증 통과', verified: '검증 통과', ok: '정상',
  healthy: '정상', invalid: '검증 실패', damaged: '손상 확인', unverified: '검증 전', passed: '검증 통과',
  verify: '파일 검증', merge: '조각 합치기', recover: '복구본 만들기', transcode: '변환', archive: '보관',
  not_checked: '검증 전', accepted: '접수됨', original: '원본', source: '원본', merged: '합친 파일', recovered: '복구본', archive_copy: '보관 복사본',
  youtube: 'YouTube', chzzk: 'CHZZK', auto: '켜짐', paused: '꺼짐', heuristic: '추정 묶음', provider: '방송 ID',
};
export function label(value?: string | null): string { return value ? labels[value] || value : '미확인'; }
export function validation(value: unknown): string {
  if (typeof value === 'string') return value;
  if (value && typeof value === 'object' && 'status' in value && typeof value.status === 'string') return value.status;
  return 'unknown';
}
export function safeLegacyLink(value: string | undefined, fallback: string): string {
  // Settings links cannot become external navigation or executable schemes.
  return value?.startsWith('/') && !value.startsWith('//') && !value.includes('\\') ? value : fallback;
}
