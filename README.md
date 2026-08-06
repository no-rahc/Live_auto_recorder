<div align="center">

# Live Auto Recorder

CHZZK·YouTube 라이브 자동 녹화 도구

[![UI checks](https://github.com/no-rahc/Live_auto_recorder/actions/workflows/ui-check.yml/badge.svg?branch=main)](https://github.com/no-rahc/Live_auto_recorder/actions/workflows/ui-check.yml)
[![Core checks](https://github.com/no-rahc/Live_auto_recorder/actions/workflows/core-check.yml/badge.svg?branch=main)](https://github.com/no-rahc/Live_auto_recorder/actions/workflows/core-check.yml)
[![Docker publish](https://github.com/no-rahc/Live_auto_recorder/actions/workflows/docker-publish.yml/badge.svg?branch=main)](https://github.com/no-rahc/Live_auto_recorder/actions/workflows/docker-publish.yml)
[![Docker pulls](https://img.shields.io/docker/pulls/no-rahc/live-auto-recorder?logo=docker&label=pulls)](https://hub.docker.com/r/no-rahc/live-auto-recorder)
[![License](https://img.shields.io/badge/license-MIT-2f81f7.svg)](LICENSE)

</div>

## 설치

```bash
git clone https://github.com/no-rahc/Live_auto_recorder.git
cd Live_auto_recorder

cp .env.example .env
mkdir -p data recordings logs tmp

docker compose -f compose.yaml pull
docker compose -f compose.yaml up -d
```

```bash
docker compose -f compose.yaml ps
docker compose -f compose.yaml logs --tail 100 recorder
```

```text
http://서버주소:5000
```

## 설정

`.env`에서 경로와 포트를 지정합니다.

| 변수 | 기본값 | 설명 |
|---|---|---|
| `LIVE_AUTO_RECORDER_IMAGE` | `no-rahc/live-auto-recorder:latest` | Docker 이미지 |
| `APP_PORT` | `5000` | 웹 포트 |
| `TZ` | `Asia/Seoul` | 시간대 |
| `LOG_LEVEL` | `info` | 로그 수준 |
| `CONFIG_PATH` | `./data` | 설정·계정·쿠키·백업 |
| `RECORDINGS_PATH` | `./recordings` | 녹화 파일 |
| `LOG_PATH` | `./logs` | 로그 |
| `TMP_PATH` | `./tmp` | 임시 파일 |

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

```bash
docker compose -f compose.yaml up -d --force-recreate
```

운영 서버에서는 `latest` 대신 확인한 버전 태그를 고정하는 편이 안전합니다.

## 저장 경로

| 호스트 경로 | 컨테이너 경로 |
|---|---|
| `CONFIG_PATH` | `/app/json` |
| `RECORDINGS_PATH` | `/app/chzzk` |
| `LOG_PATH` | `/app/logs` |
| `TMP_PATH` | `/app/tmp` |

NAS 경로는 Docker 실행 전에 호스트에 마운트합니다.

```bash
mount | grep -E 'cifs|nfs'
touch /mnt/nas/recordings/.lar-write-test
rm /mnt/nas/recordings/.lar-write-test
```

## 외부 접속

기본 설정은 `5000` 포트를 모든 인터페이스에 공개합니다. 외부에서 접속할 때는 로그인 모드와 HTTPS 리버스 프록시를 사용하세요.

리버스 프록시를 통해서만 접속한다면 포트를 로컬 주소에 바인딩할 수 있습니다.

```yaml
services:
  recorder:
    ports:
      - "127.0.0.1:5000:5000"
```

`data`, `.env`, 쿠키와 토큰 파일은 저장소에 커밋하지 마세요.

## 운영

```bash
# 상태
docker compose -f compose.yaml ps

# 최근 로그
docker compose -f compose.yaml logs --tail 200 recorder

# 실시간 로그
docker compose -f compose.yaml logs -f recorder

# 재시작
docker compose -f compose.yaml restart recorder

# 실행 이미지
docker inspect live-auto-recorder --format '{{.Config.Image}} {{.State.Status}}'
```

운영 기능과 저장소 정책은 [`docs/OPERATIONS.md`](docs/OPERATIONS.md)를 참고하세요.

## 업데이트

```bash
git pull --ff-only
docker compose -f compose.yaml pull
docker compose -f compose.yaml up -d --force-recreate
docker compose -f compose.yaml ps
```

## 롤백

`.env`의 이미지 태그를 이전 버전으로 바꾼 뒤 다시 실행합니다.

```bash
docker compose -f compose.yaml pull
docker compose -f compose.yaml up -d --force-recreate
docker compose -f compose.yaml logs --tail 100 recorder
```

## 백업

```bash
docker compose -f compose.yaml stop recorder
tar -czf live-auto-recorder-data-$(date +%Y%m%d-%H%M%S).tar.gz data
docker compose -f compose.yaml start recorder
```

최소한 `data` 디렉터리는 정기적으로 백업하세요.

## 문제 해결

```bash
docker compose -f compose.yaml ps
docker compose -f compose.yaml logs --tail 300 recorder
docker compose -f compose.yaml config
```

먼저 포트 충돌, `.env` 경로, 볼륨 권한과 NAS 마운트 상태를 확인합니다.

## 개발

```bash
python -m pip install -r requirements.txt
python app_entry.py
```

```bash
python -m compileall -q app_entry.py lar_app module
python -m unittest discover -s tests -p 'test_*_v1.py' -v
python -m unittest discover -s tests -p 'test_operations_v2.py' -v
npm install
npm run test:ui
python scripts/release.py check
```

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/OPERATIONS.md`](docs/OPERATIONS.md)
- [`docs/RELEASE.md`](docs/RELEASE.md)

## 라이선스

[MIT License](LICENSE)
