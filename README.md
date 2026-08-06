<div align="center">

# Live Auto Recorder

**CHZZK와 YouTube 라이브 방송을 자동 감지·녹화하는 셀프호스팅 운영 콘솔**

Docker Compose 기반으로 배포하며, 채널 관리부터 녹화 제어, 저장소 보호, 자동 복구, 후처리, 백업과 통계까지 하나의 웹 UI에서 운영합니다.

[![UI checks](https://github.com/no-rahc/Live_auto_recorder/actions/workflows/ui-check.yml/badge.svg?branch=main)](https://github.com/no-rahc/Live_auto_recorder/actions/workflows/ui-check.yml)
[![Core checks](https://github.com/no-rahc/Live_auto_recorder/actions/workflows/core-check.yml/badge.svg?branch=main)](https://github.com/no-rahc/Live_auto_recorder/actions/workflows/core-check.yml)
[![Docker publish](https://github.com/no-rahc/Live_auto_recorder/actions/workflows/docker-publish.yml/badge.svg?branch=main)](https://github.com/no-rahc/Live_auto_recorder/actions/workflows/docker-publish.yml)
[![Docker pulls](https://img.shields.io/docker/pulls/no-rahc/live-auto-recorder?logo=docker&label=pulls)](https://hub.docker.com/r/no-rahc/live-auto-recorder)
[![License](https://img.shields.io/badge/license-MIT-2f81f7.svg)](LICENSE)

`Docker Compose` · `linux/amd64` · `linux/arm64` · `CHZZK` · `YouTube`

[빠른 시작](#빠른-시작) · [프로덕션 구성](#프로덕션-구성) · [운영](#운영) · [업데이트와 롤백](#업데이트와-롤백) · [백업과 복원](#백업과-복원) · [개발](#개발)

</div>

> [!IMPORTANT]
> 기본 `compose.yaml`은 호스트의 모든 인터페이스에 웹 포트를 공개합니다. 인터넷이나 외부 네트워크에 노출할 때는 로그인 모드, HTTPS 리버스 프록시, 방화벽 또는 VPN을 함께 적용하세요.

## 개요

Live Auto Recorder는 개인 서버, 홈랩, NAS와 소규모 운영 환경에서 라이브 방송 녹화를 안정적으로 자동화하기 위한 웹 애플리케이션입니다. 설정, 인증정보, 로그와 녹화 결과는 컨테이너 외부 볼륨에 보관하므로 애플리케이션 업데이트와 데이터 수명주기를 분리할 수 있습니다.

### 주요 기능

| 영역 | 제공 기능 |
|---|---|
| 라이브 감지 | CHZZK·YouTube 상태 확인, 자동 대기, 개별·전체 녹화 제어 |
| 녹화 안정성 | 파일 증가 감시, 정지 탐지, 제한된 자동 재연결, 최대 녹화 시간 |
| 채널 정책 | 제목·카테고리·요일·시간대·시작 지연·화질·녹화 길이 규칙 |
| 저장소 보호 | 여유 공간 경고, 신규 녹화 차단, 정리 미리보기, 선택적 자동 정리 |
| 후처리 | 스트림 복사·인코딩 프로필, 진행 상태, 취소와 재시도 |
| 운영 관리 | 설정 백업·복원, 감사 기록, 채널별 통계와 CSV 내보내기 |
| 알림 | Telegram·Discord 녹화 실패, 저장소 경고와 자동 복구 알림 |
| 관리 UI | 데스크톱·태블릿·모바일 반응형 콘솔, 파일·쿠키·채널 관리 |

### 배포 모델

```text
브라우저
  └─ HTTP/HTTPS
      └─ Live Auto Recorder container
          ├─ /app/json   설정·계정·쿠키·운영 데이터
          ├─ /app/chzzk  녹화 결과
          ├─ /app/logs   애플리케이션 로그
          └─ /app/tmp    임시·후처리 작업 파일
```

Docker 이미지에는 Python 런타임과 `FFmpeg`, `yt-dlp`, `ytarchive`, `aria2` 등 녹화·후처리에 필요한 도구가 포함됩니다.

## 빠른 시작

### 요구 사항

- Docker Engine
- Docker Compose 플러그인
- 녹화 결과를 저장할 로컬 디스크 또는 호스트에 마운트된 NAS 경로

### 1. 저장소와 환경 파일 준비

```bash
git clone https://github.com/no-rahc/Live_auto_recorder.git
cd Live_auto_recorder
cp .env.example .env
mkdir -p data recordings logs tmp
```

### 2. 컨테이너 시작

```bash
docker compose -f compose.yaml pull
docker compose -f compose.yaml up -d
```

### 3. 상태 확인

```bash
docker compose -f compose.yaml ps
docker compose -f compose.yaml logs --tail 100 recorder
curl -fsS http://127.0.0.1:5000/ >/dev/null && echo "healthy"
```

기본 접속 주소는 다음과 같습니다.

```text
http://서버주소:5000
```

### 4. 첫 실행 체크리스트

1. **채널 관리**에서 녹화할 CHZZK 또는 YouTube 채널을 등록합니다.
2. **쿠키 관리**에서 필요한 플랫폼 인증정보를 등록합니다.
3. **설정 관리**에서 자동 녹화, 저장 경로, 화질과 후처리 설정을 확인합니다.
4. **운영 관리 → 저장소**에서 실제 녹화 볼륨과 여유 공간을 확인합니다.
5. 한 채널을 수동 녹화해 파일 생성, 쓰기 권한과 후처리 동작을 검증합니다.

## 프로덕션 구성

### 환경 변수

`.env`에서 호스트별 배포 값을 관리합니다.

| 변수 | 기본값 | 설명 |
|---|---:|---|
| `LIVE_AUTO_RECORDER_IMAGE` | `no-rahc/live-auto-recorder:latest` | 실행할 Docker 이미지 또는 고정 버전 태그 |
| `APP_PORT` | `5000` | 호스트에 공개할 웹 포트 |
| `TZ` | `Asia/Seoul` | 컨테이너 시간대 |
| `LOG_LEVEL` | `info` | 애플리케이션 로그 수준 |
| `CONFIG_PATH` | `./data` | 설정, 계정, 쿠키, 운영 정책과 백업 경로 |
| `RECORDINGS_PATH` | `./recordings` | 녹화 결과 경로 |
| `LOG_PATH` | `./logs` | 로그 경로 |
| `TMP_PATH` | `./tmp` | 임시 작업 경로 |

운영 환경에서는 `latest`보다 검증한 버전 태그를 고정하는 방식을 권장합니다.

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
docker compose -f compose.yaml ps
```

### 영속 데이터

| 호스트 경로 | 컨테이너 경로 | 내용 | 백업 우선순위 |
|---|---|---|---:|
| `CONFIG_PATH` | `/app/json` | 설정, 채널, 쿠키, 계정, 운영 정책, 작업 이력, 백업 | 필수 |
| `RECORDINGS_PATH` | `/app/chzzk` | 녹화 결과 | 운영 정책에 따라 |
| `LOG_PATH` | `/app/logs` | 애플리케이션 로그 | 선택 |
| `TMP_PATH` | `/app/tmp` | 임시 다운로드와 후처리 파일 | 불필요 |

NAS를 사용할 때는 컨테이너 시작 전에 호스트에 먼저 마운트하고 Docker가 해당 경로에 읽기·쓰기를 수행할 수 있는지 확인하세요.

```bash
mount | grep -E 'cifs|nfs'
touch /mnt/nas/recordings/.lar-write-test
rm /mnt/nas/recordings/.lar-write-test
```

### 네트워크 노출 제한

로컬 호스트의 리버스 프록시를 통해서만 접속할 경우 `compose.override.yaml`에서 포트를 루프백 주소로 제한할 수 있습니다.

```yaml
services:
  recorder:
    ports:
      - "127.0.0.1:${APP_PORT:-5000}:5000"
```

적용 후 최종 구성을 확인합니다.

```bash
docker compose -f compose.yaml -f compose.override.yaml config
docker compose -f compose.yaml -f compose.override.yaml up -d
```

### 프로덕션 체크리스트

- [ ] 검증한 Docker 이미지 버전을 고정했습니다.
- [ ] `CONFIG_PATH`와 `RECORDINGS_PATH`를 호스트 영속 경로에 연결했습니다.
- [ ] 녹화 경로의 실제 쓰기 권한과 남은 공간을 확인했습니다.
- [ ] 외부 공개 시 로그인 모드와 HTTPS를 활성화했습니다.
- [ ] `data` 백업 주기와 복원 절차를 준비했습니다.
- [ ] 저장소 경고·차단 임계값과 자동 정리 정책을 검토했습니다.

## 운영

### 일상 운영 명령

```bash
# 컨테이너와 health 상태
docker compose -f compose.yaml ps

# 최근 로그
docker compose -f compose.yaml logs --tail 200 recorder

# 실시간 로그
docker compose -f compose.yaml logs -f recorder

# 정상 재시작
docker compose -f compose.yaml restart recorder

# 실행 이미지 확인
docker compose -f compose.yaml images
docker inspect live-auto-recorder --format '{{.Config.Image}} {{.State.Status}}'
```

기본 Compose 구성에는 `restart: unless-stopped`, HTTP health check, 45초 종료 유예, JSON 로그 순환과 init 프로세스가 포함됩니다.

### 운영 관리 화면

사이드바의 **운영 관리**에서 다음 항목을 확인할 수 있습니다.

- 저장소 여유 공간과 신규 녹화 차단 상태
- 보관 기간·최대 용량 기준 삭제 대상 미리보기
- 녹화 중이거나 최근 생성된 파일을 보호하는 안전 정리
- 채널별 파일 증가 속도, 마지막 기록 시각과 재연결 상태
- 후처리 작업 진행 상태, 취소와 재시도
- 설정·채널 백업과 복원 전 안전 백업
- 최근 14일·채널별 녹화 통계와 CSV
- 채널 규칙과 변경 감사 기록

기본 보호 정책은 남은 공간 10%에서 경고하고 5% 이하에서 신규 녹화를 차단합니다. 자동 삭제는 기본적으로 꺼져 있으므로 활성화 전에 반드시 **삭제 대상 미리보기**를 확인하세요.

세부 운영 기준은 [`docs/OPERATIONS.md`](docs/OPERATIONS.md)를 참고하세요.

## 업데이트와 롤백

### 최신 버전으로 업데이트

```bash
git pull --ff-only
docker compose -f compose.yaml pull
docker compose -f compose.yaml up -d --force-recreate
docker compose -f compose.yaml ps
docker compose -f compose.yaml logs --tail 100 recorder
```

업데이트 후 이전 UI가 남아 있다면 브라우저에서 `Ctrl + Shift + R`로 캐시를 새로고침하세요.

### 특정 버전으로 롤백

1. `.env`의 `LIVE_AUTO_RECORDER_IMAGE`를 이전 정상 버전으로 변경합니다.
2. 해당 이미지를 내려받고 컨테이너를 다시 생성합니다.
3. health 상태와 최근 로그를 확인합니다.

```bash
docker compose -f compose.yaml pull
docker compose -f compose.yaml up -d --force-recreate
docker compose -f compose.yaml ps
docker compose -f compose.yaml logs --tail 100 recorder
```

설정 형식 변경이 포함된 릴리스에서 롤백할 경우 애플리케이션 버전과 함께 `data` 백업도 복원하는 것이 안전합니다.

## 백업과 복원

### 최소 백업

설정과 인증정보가 포함된 `data` 디렉터리는 반드시 백업하세요.

```bash
docker compose -f compose.yaml stop recorder
tar -czf live-auto-recorder-data-$(date +%Y%m%d-%H%M%S).tar.gz data
docker compose -f compose.yaml start recorder
```

녹화 파일까지 보호해야 한다면 `recordings`를 별도 스냅샷 또는 증분 백업 대상으로 관리하세요. 대용량 녹화 경로는 설정 백업과 분리하는 편이 효율적입니다.

> [!WARNING]
> `data` 백업에는 계정 해시, 세션 키, 플랫폼 쿠키와 알림 토큰이 포함될 수 있습니다. 백업 파일의 접근 권한과 보관 기간을 제한하세요.

### 복원 절차

1. 현재 `data` 디렉터리를 별도 위치에 한 번 더 보관합니다.
2. 컨테이너를 중지합니다.
3. 백업을 원래 `CONFIG_PATH` 위치에 복원합니다.
4. 파일 소유권과 쓰기 권한을 확인합니다.
5. 컨테이너를 시작하고 로그, 채널 설정과 녹화 상태를 확인합니다.

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
docker compose -f compose.yaml images
```

실제 이미지가 교체되었는지 확인한 뒤 브라우저에서 `Ctrl + Shift + R`을 실행하세요.
</details>

<details>
<summary><strong>방송은 시작됐지만 제목이나 상태가 늦게 갱신됩니다.</strong></summary>

최근 로그에서 플랫폼 메타데이터 오류와 인증 만료 여부를 확인하세요. 녹화 중인 채널의 메타데이터는 주기적으로 다시 조회됩니다.
</details>

<details>
<summary><strong>저장소가 위험 또는 녹화 차단으로 표시됩니다.</strong></summary>

운영 관리에서 실제 녹화 경로와 남은 공간을 확인하세요. 자동 삭제를 활성화하기 전에 삭제 대상 미리보기를 실행하고 필요한 파일은 별도 경로로 이동하세요.
</details>

<details>
<summary><strong>NAS 용량이 잘못 표시되거나 파일을 쓸 수 없습니다.</strong></summary>

호스트의 NAS 마운트 상태와 `.env`의 `RECORDINGS_PATH`를 확인하세요. 컨테이너 내부 경로가 아니라 **호스트 마운트 경로**를 지정해야 합니다.
</details>

<details>
<summary><strong>로그인이 일시 제한되었습니다.</strong></summary>

같은 클라이언트에서 10분 동안 로그인에 5회 실패하면 추가 시도가 일시 제한됩니다. 제한 시간이 지난 후 다시 시도하고, 리버스 프록시가 실제 클라이언트 주소를 올바르게 전달하는지 확인하세요.
</details>

## 보안

- 신뢰할 수 없는 네트워크에서는 로그인 모드를 반드시 활성화하세요.
- 인터넷 공개 시 HTTPS 리버스 프록시, 방화벽 또는 VPN을 사용하세요.
- `data`, `.env`, 쿠키, 토큰과 백업 파일을 저장소에 커밋하지 마세요.
- 파일 관리 기능은 인증된 배포에서만 활성화하세요.
- 민감정보 포함 백업은 꼭 필요한 경우에만 만들고 접근 권한을 제한하세요.
- Docker Hub 토큰과 서비스 인증정보를 이슈, 로그 또는 채팅에 붙여 넣지 마세요.

취약점이나 민감정보 노출을 발견했다면 공개 이슈에 값을 첨부하지 말고, 먼저 해당 인증정보를 폐기·재발급한 뒤 최소한의 재현 정보만 공유하세요.

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

### 관련 문서

- 아키텍처: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- 운영 정책: [`docs/OPERATIONS.md`](docs/OPERATIONS.md)
- 릴리스 절차: [`docs/RELEASE.md`](docs/RELEASE.md)

### 릴리스

루트의 `VERSION`이 런타임, UI와 Docker 태그의 기준입니다.

```bash
python scripts/release.py bump --summary "변경 내용을 작성합니다."
python scripts/release.py check
```

`main`에 병합되면 Docker 게시 워크플로가 다음 태그를 생성합니다.

```text
no-rahc/live-auto-recorder:latest
no-rahc/live-auto-recorder:vX.Y.Z
```

## 라이선스와 이용 책임

이 프로젝트는 [MIT License](LICENSE)로 배포됩니다.

라이브 방송의 녹화, 보관, 공유와 재배포 시 각 플랫폼의 이용약관과 저작권, 초상권, 개인정보 보호 관련 법률을 준수해야 합니다. 프로젝트 사용으로 발생하는 법적·운영상 책임은 사용자에게 있습니다.
