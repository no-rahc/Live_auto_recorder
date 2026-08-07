<div align="center">

# Live Auto Recorder

CHZZK · YouTube 라이브 자동 녹화 도구

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

접속 주소: `http://127.0.0.1:5000`

## 설정

주요 값은 `.env`에서 변경할 수 있습니다.

| 변수 | 기본값 |
|---|---|
| `LIVE_AUTO_RECORDER_IMAGE` | `yeowoonlee/live-auto-recorder:latest` |
| `APP_PORT` | `5000` |
| `TZ` | `Asia/Seoul` |
| `CONFIG_PATH` | `./data` |
| `RECORDINGS_PATH` | `./recordings` |
| `LOG_PATH` | `./logs` |
| `TMP_PATH` | `./tmp` |

설정 변경 후에는 컨테이너를 다시 생성합니다.

```bash
docker compose up -d --force-recreate
```

## 업데이트

```bash
git pull --ff-only
docker compose pull
docker compose up -d --force-recreate
```

## 문서

- [운영 가이드](docs/OPERATIONS.md)
- [구조](docs/ARCHITECTURE.md)
- [보안](SECURITY.md)
- [기여](CONTRIBUTING.md)

## 라이선스

[MIT License](LICENSE)
