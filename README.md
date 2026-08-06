<div align="center">

# Live Auto Recorder

CHZZK·YouTube 라이브 자동 녹화 도구

[![UI checks](https://github.com/no-rahc/Live_auto_recorder/actions/workflows/ui-check.yml/badge.svg?branch=main)](https://github.com/no-rahc/Live_auto_recorder/actions/workflows/ui-check.yml)
[![Core checks](https://github.com/no-rahc/Live_auto_recorder/actions/workflows/core-check.yml/badge.svg?branch=main)](https://github.com/no-rahc/Live_auto_recorder/actions/workflows/core-check.yml)
[![Docker pulls](https://img.shields.io/docker/pulls/yeowoonlee/live-auto-recorder?logo=docker&label=pulls)](https://hub.docker.com/r/yeowoonlee/live-auto-recorder)

</div>

## 설치

```bash
git clone https://github.com/no-rahc/Live_auto_recorder.git
cd Live_auto_recorder
cp .env.example .env
mkdir -p data recordings logs tmp

docker compose pull
docker compose up -d
```

```bash
docker compose ps
docker compose logs --tail 100 recorder
```

기본 접속 주소는 `http://127.0.0.1:5000`입니다. 처음 접속하면 계정을 만든 뒤 로그인합니다.

## 설정

`.env`에서 포트와 저장 경로를 변경할 수 있습니다.

| 변수 | 기본값 | 설명 |
|---|---|---|
| `LIVE_AUTO_RECORDER_IMAGE` | `yeowoonlee/live-auto-recorder:latest` | Docker 이미지 |
| `APP_BIND_ADDRESS` | `127.0.0.1` | 호스트 바인딩 주소 |
| `APP_PORT` | `5000` | 웹 포트 |
| `TZ` | `Asia/Seoul` | 시간대 |
| `LOG_LEVEL` | `info` | 로그 수준 |
| `ALLOW_ANONYMOUS` | `false` | 로그인 없이 사용하는 모드 |
| `SESSION_HTTPS_ONLY` | `false` | 세션 쿠키의 Secure 속성 |
| `ALLOW_SECRET_BACKUPS` | `false` | 쿠키·계정·토큰 포함 백업 허용 |
| `CONFIG_PATH` | `./data` | 설정·계정·쿠키·백업 |
| `RECORDINGS_PATH` | `./recordings` | 녹화 파일 |
| `LOG_PATH` | `./logs` | 로그 |
| `TMP_PATH` | `./tmp` | 임시 파일 |

다른 기기에서 접속하려면 로그인 설정을 마친 뒤 다음 값을 사용합니다.

```env
APP_BIND_ADDRESS=0.0.0.0
```

HTTPS 리버스 프록시 뒤에서 운영할 때는 다음 값도 켭니다.

```env
SESSION_HTTPS_ONLY=true
```

변경 후 컨테이너를 다시 생성합니다.

```bash
docker compose up -d --force-recreate
```

`ALLOW_ANONYMOUS=true`는 외부에 노출되지 않은 신뢰할 수 있는 네트워크에서만 사용하세요. 운영 관리와 백업 기능은 익명 모드에서도 계정 로그인이 필요합니다.

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

## 운영

```bash
# 상태
docker compose ps

# 로그
docker compose logs -f recorder

# 재시작
docker compose restart recorder

# 실행 이미지
docker inspect live-auto-recorder --format '{{.Config.Image}} {{.State.Status}}'
```

상태 확인 주소는 `/healthz`입니다. 운영 기능과 저장소 정책은 [`docs/OPERATIONS.md`](docs/OPERATIONS.md)를 참고하세요.

## 업데이트

```bash
git pull --ff-only
docker compose pull
docker compose up -d --force-recreate
docker compose ps
```

운영 서버에서는 `latest` 대신 Git 태그와 같은 버전 이미지를 고정하는 편이 안전합니다.

```env
LIVE_AUTO_RECORDER_IMAGE=yeowoonlee/live-auto-recorder:vX.Y.Z
```

## 롤백

`.env`의 이미지 태그를 이전 버전으로 바꾼 뒤 다시 실행합니다.

```bash
docker compose pull
docker compose up -d --force-recreate
docker compose logs --tail 100 recorder
```

## 백업

```bash
docker compose stop recorder
tar -czf live-auto-recorder-data-$(date +%Y%m%d-%H%M%S).tar.gz data
docker compose start recorder
```

최소한 `data` 디렉터리는 정기적으로 백업하세요. 쿠키와 토큰을 포함한 백업은 `ALLOW_SECRET_BACKUPS=true`를 명시한 경우에만 만들 수 있습니다.

## 문제 해결

```bash
docker compose ps
docker compose logs --tail 300 recorder
docker compose config
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
npm ci
npm run test:ui
python scripts/release.py check
```

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/OPERATIONS.md`](docs/OPERATIONS.md)
- [`docs/RELEASE.md`](docs/RELEASE.md)
- [`SECURITY.md`](SECURITY.md)
- [`CONTRIBUTING.md`](CONTRIBUTING.md)
- [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)

## 라이선스

[MIT License](LICENSE)
