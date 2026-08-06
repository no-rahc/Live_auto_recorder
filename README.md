<div align="center">

# Live Auto Recorder

**CHZZK와 YouTube 라이브 방송을 자동 감지·녹화하는 셀프호스팅 운영 콘솔**

채널 등록부터 녹화 제어, 저장소 보호, 자동 복구, 후처리, 백업, 통계와 파일 관리까지 하나의 반응형 웹 UI에서 운영합니다.

[![UI checks](https://img.shields.io/github/actions/workflow/status/no-rahc/Live_auto_recorder/ui-check.yml?branch=main&label=UI%20checks)](../../actions/workflows/ui-check.yml)
[![Core checks](https://img.shields.io/github/actions/workflow/status/no-rahc/Live_auto_recorder/core-check.yml?branch=main&label=Core%20checks)](../../actions/workflows/core-check.yml)
[![Docker publish](https://img.shields.io/github/actions/workflow/status/no-rahc/Live_auto_recorder/docker-publish.yml?branch=main&label=Docker%20publish)](../../actions/workflows/docker-publish.yml)
[![Docker pulls](https://img.shields.io/docker/pulls/no-rahc/live-auto-recorder?label=Docker%20pulls)](https://hub.docker.com/r/no-rahc/live-auto-recorder)
[![License](https://img.shields.io/github/license/no-rahc/Live_auto_recorder)](LICENSE)

[빠른 시작](#빠른-시작) · [운영 구성](#운영-구성) · [업데이트와 롤백](#업데이트와-롤백) · [백업](#백업) · [문제 해결](#문제-해결) · [개발](#개발)

</div>

---

## 프로젝트 개요

Live Auto Recorder는 개인 서버, 홈랩, NAS 또는 소규모 운영 환경에서 라이브 방송 녹화를 안정적으로 자동화하기 위한 웹 애플리케이션입니다. 기본 사용 방식은 Docker Compose이며, 설정과 녹화 파일은 컨테이너 외부의 호스트 볼륨에 저장됩니다.

### 핵심 기능

| 영역 | 기능 |
|---|---|
| 라이브 감지 | CHZZK·YouTube 채널 상태 확인, 자동 대기, 개별·전체 녹화 제어 |
| 녹화 안정성 | 파일 증가 감시, 정지 감지, 제한된 자동 재연결, 최대 녹화 시간 |
| 채널 정책 | 제목·카테고리·요일·시간대·시작 지연·화질·녹화 길이 규칙 |
| 저장소 보호 | 남은 공간 경고, 신규 녹화 차단, 정리 미리보기, 선택적 자동 정리 |
| 후처리 | 스트림 복사·인코딩 프로필, 작업 상태, 취소와 재시도 |
| 운영 관리 | 설정 백업·복원, 감사 기록, 채널별 통계와 CSV 내보내기 |
| 알림 | Telegram·Discord 녹화 실패, 저장소 경고와 자동 복구 알림 |
| 관리 UI | 데스크톱·태블릿·모바일 반응형 콘솔, 파일·쿠키·채널 관리 |

### 지원 환경

| 항목 | 지원 |
|---|---|
| 컨테이너 아키텍처 | `linux/amd64`, `linux/arm64` |
| 배포 방식 | Docker Engine + Docker Compose 플러그인 |
| 브라우저 | 최신 Chromium, Firefox, Safari 계열 |
| 저장소 | 로컬 디스크, Docker 볼륨, 호스트에 마운트된 NFS/CIFS NAS |
| 기본 이미지 | `no-rahc/live-auto-recorder:latest` |

Docker 이미지에는 애플리케이션 실행에 필요한 Python 패키지와 녹화·후처리 도구가 포함됩니다.

## 빠른 시작

### 요구 사항

- Docker Engine
- Docker Compose 플러그인
- 설정과 녹화 파일을 보관할 충분한 디스크 공간

### 1. 저장소 준비

```bash
git clone https://github.com/no-rahc/Live_auto_recorder.git
cd Live_auto_recorder
cp .env.example .env
mkdir -p data recordings logs tmp
```

### 2. 컨테이너 실행

```bash
docker compose -f compose.yaml pull
docker compose -f compose.yaml up -d
```

### 3. 상태 확인

```bash
docker compose -f compose.yaml ps
docker compose -f compose.yaml logs --tail 100 recorder
```

브라우저에서 다음 주소로 접속합니다.

```text
http://서버주소:5000
```

### 4. 첫 실행 체크리스트

1. **채널 관리**에서 녹화할 채널을 등록합니다.
2. **쿠키 관리**에서 필요한 플랫폼 인증정보를 등록합니다.
3. **설정 관리**에서 자동녹화, 저장 경로, 품질과 후처리를 확인합니다.
4. **운영 관리 → 저장소**에서 실제 녹화 볼륨과 여유 공간을 확인합니다.
5. 한 채널을 수동 녹화해 파일 생성과 쓰기 권한을 검증합니다.

## 운영 구성

### 환경 변수

`.env`에서 다음 값을 관리합니다.

| 변수 | 기본값 | 설명 |
|---|---:|---|
| `LIVE_AUTO_RECORDER_IMAGE` | `no-rahc/live-auto-recorder:latest` | 실행할 이미지 또는 고정 버전 태그 |
| `APP_PORT` | `5000` | 호스트에 공개할 웹 포트 |
| `TZ` | `Asia/Seoul` | 컨테이너 시간대 |
| `LOG_LEVEL` | `info` | 애플리케이션 로그 수준 |
| `CONFIG_PATH` | `./data` | 설정, 계정, 쿠키, 운영 정책과 백업 경로 |
| `RECORDINGS_PATH` | `./recordings` | 녹화 결과 경로 |
| `LOG_PATH` | `./logs` | 로그 경로 |
| `TMP_PATH` | `./tmp` | 임시 작업 경로 |

예시:

```env
LIVE_AUTO_RECORDER_IMAGE=no-rahc/live-auto-recorder:v1.1.18
APP_PORT=5000
TZ=Asia/Seoul
LOG_LEVEL=info
CONFIG_PATH=/srv/live-auto-recorder/data
RECORDINGS_PATH=/mnt/nas/recordings
LOG_PATH=/srv/live-auto-recorder/logs
TMP_PATH=/srv/live-auto-recorder/tmp
```

변경 후 컨테이너를 다시 생성합니다.

```bash
docker compose -f compose.yaml up -d --force-recreate
```

### 볼륨과 데이터

| 호스트 경로 | 컨테이너 경로 | 내용 | 백업 우선순위 |
|---|---|---|---:|
| `./data` | `/app/json` | 설정, 채널, 쿠키, 계정, 운영 정책, 작업 이력, 백업 | 필수 |
| `./recordings` | `/app/chzzk` | 녹화 결과 | 필요에 따라 |
| `./logs` | `/app/logs` | 애플리케이션 로그 | 선택 |
| `./tmp` | `/app/tmp` | 임시 다운로드와 후처리 파일 | 불필요 |

NAS를 사용할 때는 컨테이너를 시작하기 전에 호스트에 먼저 마운트하고 Docker 프로세스가 해당 경로에 읽기·쓰기를 수행할 수 있는지 확인하세요.

```bash
mount | grep -E 'cifs|nfs'
touch /mnt/nas/recordings/.lar-write-test
rm /mnt/nas/recordings/.lar-write-test
```

### 로컬 모드와 로그인 모드

기본 로컬 모드에서는 로그인 없이 콘솔을 사용하며 사이드바에는 탐색 메뉴만 표시됩니다. 이 방식은 신뢰할 수 있는 로컬 네트워크에서만 사용하세요.

외부 네트워크나 리버스 프록시를 통해 공개할 때는 다음을 적용해야 합니다.

1. **설정 관리 → 시스템·보안**에서 로그인 모드를 활성화합니다.
2. 관리자 계정을 생성합니다.
3. HTTPS 리버스 프록시를 사용합니다.
4. 방화벽 또는 접근 제어 목록으로 접속 대상을 제한합니다.
5. 파일 관리 기능은 인증된 배포에서만 활성화합니다.

`compose.yaml`의 기본 포트 매핑은 호스트의 모든 인터페이스에 포트를 공개합니다. 로컬 머신에서만 접속할 경우 `ports`를 다음처럼 제한할 수 있습니다.

```yaml
ports:
  - "127.0.0.1:5000:5000"
```

### 운영 관리

사이드바의 **운영 관리**에서 다음 항목을 확인할 수 있습니다.

- 저장소 여유 공간과 신규 녹화 차단 상태
- 보관 기간·최대 용량 기준 삭제 대상 미리보기
- 녹화 중이거나 최근 생성된 파일을 보호하는 안전 정리
- 채널별 파일 증가 속도, 마지막 기록 시각과 재연결 상태
- 후처리 작업 진행 상태, 취소와 재시도
- 설정·채널 백업과 복원 전 안전 백업
- 최근 14일·채널별 녹화 통계와 CSV
- 채널 규칙과 변경 감사 기록

기본 보호 정책은 남은 공간 10%에서 경고하고 5% 이하에서 신규 녹화를 차단합니다. 자동 삭제는 기본적으로 꺼져 있으며, 활성화하기 전에 반드시 **삭제 대상 미리보기**를 확인하세요.

세부 안전 기준은 [`docs/OPERATIONS.md`](docs/OPERATIONS.md)를 참고하세요.

## 일상 운영 명령

```bash
# 상태와 health 확인
docker compose -f compose.yaml ps

# 최근 로그
docker compose -f compose.yaml logs --tail 200 recorder

# 실시간 로그
docker compose -f compose.yaml logs -f recorder

# 정상 재시작
docker compose -f compose.yaml restart recorder

# 이미지와 컨테이너 확인
docker compose -f compose.yaml images
docker inspect live-auto-recorder --format '{{.Config.Image}} {{.State.Status}}'
```

Compose 구성에는 `restart: unless-stopped`, HTTP health check, 45초 종료 유예, JSON 로그 순환과 init 프로세스가 포함됩니다.

## 업데이트와 롤백

### 최신 버전으로 업데이트

```bash
git pull --ff-only
docker compose -f compose.yaml pull
docker compose -f compose.yaml up -d --force-recreate
docker compose -f compose.yaml ps
```

업데이트 후 이전 화면이 남아 있다면 브라우저에서 `Ctrl + Shift + R`로 캐시를 새로고침하세요.

### 특정 버전 고정

운영 환경에서는 `latest` 대신 검증한 버전 태그를 고정하는 방식이 더 예측 가능합니다.

```env
LIVE_AUTO_RECORDER_IMAGE=no-rahc/live-auto-recorder:v1.1.18
```

### 롤백

1. `.env`의 이미지 태그를 이전 정상 버전으로 변경합니다.
2. 해당 이미지를 내려받고 컨테이너를 다시 생성합니다.

```bash
docker compose -f compose.yaml pull
docker compose -f compose.yaml up -d --force-recreate
docker compose -f compose.yaml logs --tail 100 recorder
```

설정 형식 변경이 포함된 릴리스에서 롤백할 경우, 애플리케이션 버전과 함께 `data` 백업도 복원하는 것이 안전합니다.

## 백업

### 최소 백업

설정과 인증정보가 포함된 `data` 디렉터리는 반드시 백업하세요.

```bash
docker compose -f compose.yaml stop recorder
tar -czf live-auto-recorder-data-$(date +%Y%m%d-%H%M%S).tar.gz data
docker compose -f compose.yaml start recorder
```

녹화 파일까지 보호해야 한다면 `recordings`를 별도 스냅샷 또는 증분 백업 대상으로 관리하세요. 대용량 녹화 경로는 설정 백업과 분리하는 편이 효율적입니다.

### 복원 전 확인

- 현재 `data` 디렉터리를 별도 위치에 한 번 더 보관합니다.
- 복원본의 파일 소유권과 쓰기 권한을 확인합니다.
- 컨테이너를 중지한 상태에서 복원합니다.
- 복원 후 로그와 채널 설정을 확인한 뒤 녹화를 시작합니다.

## 문제 해결

<details>
<summary><strong>컨테이너가 시작되지 않습니다.</strong></summary>

```bash
docker compose -f compose.yaml ps
docker compose -f compose.yaml logs --tail 300 recorder
docker compose -f compose.yaml config
```

경로 오타, 포트 충돌, 볼륨 권한과 잘못된 `.env` 값을 먼저 확인하세요.
</details>

<details>
<summary><strong>업데이트 후 이전 UI가 보입니다.</strong></summary>

```bash
docker compose -f compose.yaml pull
docker compose -f compose.yaml up -d --force-recreate
```

브라우저에서 `Ctrl + Shift + R`을 실행하고, `docker compose images`로 실제 이미지가 교체되었는지 확인하세요.
</details>

<details>
<summary><strong>방송은 시작됐지만 제목이나 상태가 늦게 갱신됩니다.</strong></summary>

최근 로그에서 플랫폼 메타데이터 오류와 인증 만료 여부를 확인하세요. 녹화 중인 채널의 메타데이터는 주기적으로 다시 조회되며, 준비 상태 문구가 반환되면 빠른 재확인을 수행합니다.
</details>

<details>
<summary><strong>저장소가 위험 또는 녹화 차단으로 표시됩니다.</strong></summary>

운영 관리에서 실제 녹화 경로와 남은 공간을 확인하세요. 자동 삭제를 활성화하기 전에 삭제 대상 미리보기를 실행하고, 필요한 파일은 별도 경로로 이동하세요.
</details>

<details>
<summary><strong>NAS 용량이 잘못 표시되거나 파일을 쓸 수 없습니다.</strong></summary>

호스트의 NAS 마운트 상태와 `.env`의 `RECORDINGS_PATH`를 확인하세요. 컨테이너 내부 경로가 아니라 **호스트 마운트 경로**를 지정해야 합니다.
</details>

<details>
<summary><strong>로그인이 잠겼습니다.</strong></summary>

같은 클라이언트에서 10분 동안 로그인에 5회 실패하면 추가 시도가 일시 제한됩니다. 제한 시간이 지난 후 다시 시도하고, 리버스 프록시가 실제 클라이언트 주소를 올바르게 전달하는지 확인하세요.
</details>

## 개발

### 로컬 실행

릴리스 버전, 미들웨어와 전역 UI 자산이 모두 적용되도록 `app_entry.py`를 실행합니다.

```bash
python -m pip install -r requirements.txt
python app_entry.py
```

기본 개발 주소는 `http://127.0.0.1:5000`입니다.

### 검사

```bash
python -m compileall -q app_entry.py lar_app module
python -m unittest discover -s tests -p 'test_*_v1.py' -v
python -m unittest discover -s tests -p 'test_operations_v2.py' -v
npm install
npm run test:ui
python scripts/release.py check
```

### 프로젝트 구조

```text
app_entry.py       실행 진입점과 호환 export
lar_app/           앱 조립, 버전, 서버 설정, 미들웨어, UI 자산 매니페스트
module/            녹화, 플랫폼, 저장소, 후처리와 운영 도메인
templates/         Jinja 템플릿과 CSS·JavaScript 자산
tests/             Python 단위 검사와 Playwright 반응형 검사
docs/              운영, 릴리스와 아키텍처 문서
scripts/           릴리스 자동화와 유지보수 도구
```

전역 CSS와 JavaScript는 `lar_app/web/assets.py`의 매니페스트에 등록합니다. 서버 조립과 HTTP 계층은 `lar_app/`, 실제 녹화 도메인은 `module/`에 두는 것을 원칙으로 합니다.

- 아키텍처: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- 운영 정책: [`docs/OPERATIONS.md`](docs/OPERATIONS.md)
- 릴리스 절차: [`docs/RELEASE.md`](docs/RELEASE.md)

### 릴리스

루트의 `VERSION`이 런타임, UI, Docker 태그의 기준입니다.

```bash
python scripts/release.py bump --summary "변경 내용을 작성합니다."
python scripts/release.py check
```

`main`에 병합되면 Docker 게시 워크플로가 다음 태그를 생성합니다.

```text
no-rahc/live-auto-recorder:latest
no-rahc/live-auto-recorder:vX.Y.Z
```

## 보안

- `data`에는 계정 해시, 세션 키, 플랫폼 쿠키, 알림 토큰과 백업이 포함될 수 있습니다.
- `data`, `.env`, 쿠키와 토큰 파일을 공개 저장소에 커밋하지 마세요.
- 인터넷에 공개할 때는 로그인 모드, HTTPS, 방화벽 또는 VPN을 함께 사용하세요.
- 민감정보 포함 백업은 꼭 필요한 경우에만 만들고 접근 권한과 보관 기간을 제한하세요.
- Docker Hub 토큰과 서비스 인증정보를 이슈, 로그 또는 채팅에 붙여 넣지 마세요.

취약점이나 민감정보 노출을 발견했다면 공개 이슈에 값을 첨부하지 말고, 먼저 인증정보를 폐기·재발급한 뒤 최소한의 재현 정보만 공유하세요.

## 라이선스와 이용 책임

이 프로젝트는 [MIT License](LICENSE)로 배포됩니다.

라이브 방송의 녹화, 보관, 공유와 재배포 시 각 플랫폼의 이용약관과 저작권, 초상권, 개인정보 보호 관련 법률을 준수해야 합니다. 프로젝트 사용으로 발생하는 법적·운영상 책임은 사용자에게 있습니다.
