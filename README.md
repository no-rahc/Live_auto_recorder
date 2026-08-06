<div align="center">

# Live Auto Recorder

CHZZK와 YouTube 라이브 방송을 자동으로 확인하고 녹화하는 웹 애플리케이션입니다.

[![UI checks](https://github.com/no-rahc/Live_auto_recorder/actions/workflows/ui-check.yml/badge.svg?branch=main)](https://github.com/no-rahc/Live_auto_recorder/actions/workflows/ui-check.yml)
[![Core checks](https://github.com/no-rahc/Live_auto_recorder/actions/workflows/core-check.yml/badge.svg?branch=main)](https://github.com/no-rahc/Live_auto_recorder/actions/workflows/core-check.yml)
[![Docker publish](https://github.com/no-rahc/Live_auto_recorder/actions/workflows/docker-publish.yml/badge.svg?branch=main)](https://github.com/no-rahc/Live_auto_recorder/actions/workflows/docker-publish.yml)
[![Docker pulls](https://img.shields.io/docker/pulls/no-rahc/live-auto-recorder?logo=docker&label=pulls)](https://hub.docker.com/r/no-rahc/live-auto-recorder)
[![License](https://img.shields.io/badge/license-MIT-2f81f7.svg)](LICENSE)

</div>

## 소개

Live Auto Recorder는 개인 서버나 NAS에서 CHZZK·YouTube 방송을 자동으로 녹화하기 위해 만든 프로젝트입니다.

채널 등록, 녹화 시작과 중지, 쿠키 관리, 파일 관리, 저장소 확인, 후처리와 백업을 웹 화면에서 처리할 수 있습니다. 기본 실행 방식은 Docker Compose이며 설정과 녹화 파일은 호스트에 그대로 남습니다.

## 주요 기능

- CHZZK·YouTube 라이브 상태 확인 및 자동 녹화
- 채널별 녹화 활성화, 화질, 저장 경로 설정
- 제목, 카테고리, 요일과 시간대 기반 녹화 규칙
- 녹화 파일 증가 감시와 제한된 자동 재연결
- 저장 공간 경고, 신규 녹화 차단, 정리 대상 미리보기
- FFmpeg 기반 스트림 복사와 인코딩 후처리
- 설정 백업·복원, 녹화 통계, 감사 기록
- Telegram·Discord 알림
- 데스크톱과 모바일을 지원하는 관리 화면

지원 아키텍처는 `linux/amd64`, `linux/arm64`입니다.

## 빠른 시작

### 준비할 것

- Docker Engine
- Docker Compose 플러그인
- 녹화 파일을 저장할 디스크 또는 NAS 경로

### 실행

```bash
git clone https://github.com/no-rahc/Live_auto_recorder.git
cd Live_auto_recorder

cp .env.example .env
mkdir -p data recordings logs tmp

docker compose -f compose.yaml pull
docker compose -f compose.yaml up -d
```

실행 상태와 로그를 확인합니다.

```bash
docker compose -f compose.yaml ps
docker compose -f compose.yaml logs --tail 100 recorder
```

브라우저에서 아래 주소로 접속합니다.

```text
http://서버주소:5000
```

처음 실행한 뒤에는 다음 순서로 확인하면 됩니다.

1. 채널을 등록합니다.
2. 필요한 경우 CHZZK 또는 YouTube 쿠키를 등록합니다.
3. 저장 경로와 녹화 품질을 확인합니다.
4. 한 채널을 수동 녹화해 파일이 정상적으로 생성되는지 확인합니다.

## 설정

배포 환경에 따라 `.env` 값을 수정합니다.

| 변수 | 기본값 | 설명 |
|---|---|---|
| `LIVE_AUTO_RECORDER_IMAGE` | `no-rahc/live-auto-recorder:latest` | 사용할 Docker 이미지 |
| `APP_PORT` | `5000` | 웹 포트 |
| `TZ` | `Asia/Seoul` | 컨테이너 시간대 |
| `LOG_LEVEL` | `info` | 로그 수준 |
| `CONFIG_PATH` | `./data` | 설정과 계정, 쿠키, 백업 저장 경로 |
| `RECORDINGS_PATH` | `./recordings` | 녹화 파일 저장 경로 |
| `LOG_PATH` | `./logs` | 로그 저장 경로 |
| `TMP_PATH` | `./tmp` | 임시 파일 경로 |

예시:

```env
LIVE_AUTO_RECORDER_IMAGE=no-rahc/live-auto-recorder:vX.Y.Z
APP_PORT=5000
TZ=Asia/Seoul
LOG_LEVEL=info
CONFIG_PATH=/srv/live-auto-recorder/data
RECORDINGS_PATH=/mnt/nas/recordings
LOG_PATH=/srv/live-auto-recorder/logs
TMP_PATH=/srv/live-auto-recorder/tmp
```

운영 중인 서버에서는 `latest`보다 확인한 버전 태그를 고정하는 편이 안전합니다.

설정을 바꾼 뒤 컨테이너를 다시 생성합니다.

```bash
docker compose -f compose.yaml up -d --force-recreate
```

## 저장 경로

| 호스트 경로 | 컨테이너 경로 | 내용 |
|---|---|---|
| `CONFIG_PATH` | `/app/json` | 설정, 채널, 계정, 쿠키, 운영 데이터와 백업 |
| `RECORDINGS_PATH` | `/app/chzzk` | 녹화 결과 |
| `LOG_PATH` | `/app/logs` | 애플리케이션 로그 |
| `TMP_PATH` | `/app/tmp` | 임시 다운로드와 후처리 파일 |

NAS를 사용할 때는 Docker를 실행하기 전에 호스트에 먼저 마운트해야 합니다. 컨테이너 내부 경로가 아니라 호스트의 마운트 경로를 `RECORDINGS_PATH`에 지정합니다.

```bash
mount | grep -E 'cifs|nfs'
touch /mnt/nas/recordings/.lar-write-test
rm /mnt/nas/recordings/.lar-write-test
```

## 외부 접속

기본 `compose.yaml`은 `5000` 포트를 모든 인터페이스에 공개합니다.

로컬 네트워크 밖에서 접속할 경우에는 로그인 모드를 켜고 HTTPS 리버스 프록시, 방화벽 또는 VPN을 함께 사용하는 것을 권장합니다.

리버스 프록시를 통해서만 접속한다면 포트를 로컬 주소에만 바인딩할 수 있습니다.

```yaml
services:
  recorder:
    ports:
      - "127.0.0.1:5000:5000"
```

`data` 디렉터리에는 계정 정보, 세션 키, 플랫폼 쿠키와 알림 토큰이 포함될 수 있으므로 외부에 공개하거나 저장소에 커밋하지 마세요.

## 운영

자주 사용하는 명령은 아래와 같습니다.

```bash
# 상태 확인
docker compose -f compose.yaml ps

# 최근 로그
docker compose -f compose.yaml logs --tail 200 recorder

# 실시간 로그
docker compose -f compose.yaml logs -f recorder

# 재시작
docker compose -f compose.yaml restart recorder

# 실행 중인 이미지 확인
docker inspect live-auto-recorder --format '{{.Config.Image}} {{.State.Status}}'
```

관리 화면의 **운영 관리** 메뉴에서는 저장 공간, 녹화 상태, 후처리 작업, 백업, 통계와 채널 규칙을 확인할 수 있습니다.

기본 저장소 정책은 남은 공간 10%에서 경고하고 5% 이하에서 새 녹화를 막습니다. 자동 정리는 기본적으로 꺼져 있습니다. 활성화하기 전에 정리 대상 미리보기를 먼저 확인하세요.

자세한 내용은 [`docs/OPERATIONS.md`](docs/OPERATIONS.md)에 정리되어 있습니다.

## 업데이트

```bash
git pull --ff-only
docker compose -f compose.yaml pull
docker compose -f compose.yaml up -d --force-recreate
docker compose -f compose.yaml ps
```

업데이트 뒤 이전 화면이 계속 보이면 브라우저에서 강력 새로고침을 실행하고 현재 이미지가 교체되었는지 확인합니다.

```bash
docker compose -f compose.yaml images
```

## 롤백

`.env`의 이미지 태그를 이전 버전으로 바꾼 뒤 컨테이너를 다시 생성합니다.

```bash
docker compose -f compose.yaml pull
docker compose -f compose.yaml up -d --force-recreate
docker compose -f compose.yaml logs --tail 100 recorder
```

설정 형식이 변경된 버전에서 롤백할 때는 애플리케이션 이미지뿐 아니라 `data` 백업도 함께 복원하는 것이 좋습니다.

## 백업

최소한 `data` 디렉터리는 정기적으로 백업하세요.

```bash
docker compose -f compose.yaml stop recorder
tar -czf live-auto-recorder-data-$(date +%Y%m%d-%H%M%S).tar.gz data
docker compose -f compose.yaml start recorder
```

녹화 파일은 용량이 크기 때문에 설정 백업과 분리해 스냅샷이나 증분 백업으로 관리하는 편이 낫습니다.

복원할 때는 컨테이너를 중지하고 현재 데이터를 한 번 더 보관한 뒤 진행하세요.

## 문제 해결

### 컨테이너가 시작되지 않을 때

```bash
docker compose -f compose.yaml ps
docker compose -f compose.yaml logs --tail 300 recorder
docker compose -f compose.yaml config
```

포트 충돌, `.env` 경로, 볼륨 권한을 먼저 확인합니다.

### 방송 상태나 제목 갱신이 늦을 때

플랫폼 쿠키가 만료되지 않았는지 확인하고 로그에서 메타데이터 요청 오류를 찾습니다.

### NAS 용량이 다르게 보이거나 파일을 쓸 수 없을 때

호스트의 NAS 마운트 상태와 `RECORDINGS_PATH`를 확인합니다. Docker가 해당 경로에 쓸 수 있는지도 함께 확인해야 합니다.

### 로그인이 일시 제한되었을 때

같은 클라이언트에서 10분 동안 로그인에 5회 실패하면 추가 시도가 잠시 제한됩니다. 제한 시간이 지난 뒤 다시 시도하세요.

## 개발

```bash
python -m pip install -r requirements.txt
python app_entry.py
```

검사 명령:

```bash
python -m compileall -q app_entry.py lar_app module
python -m unittest discover -s tests -p 'test_*_v1.py' -v
python -m unittest discover -s tests -p 'test_operations_v2.py' -v
npm install
npm run test:ui
python scripts/release.py check
```

프로젝트 구조:

```text
app_entry.py       실행 진입점
lar_app/           앱 조립, 서버 설정, 미들웨어, 공통 웹 자산
module/            녹화, 플랫폼, 저장, 후처리와 운영 기능
templates/         Jinja 템플릿과 CSS·JavaScript
tests/             Python 단위 테스트와 Playwright UI 테스트
docs/              운영, 릴리스, 아키텍처 문서
scripts/           릴리스와 유지보수 스크립트
```

관련 문서:

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/OPERATIONS.md`](docs/OPERATIONS.md)
- [`docs/RELEASE.md`](docs/RELEASE.md)

## 라이선스

[MIT License](LICENSE)

라이브 방송을 녹화하거나 공유할 때는 각 플랫폼의 이용약관과 저작권, 개인정보 관련 법률을 확인하세요.
