<div align="center">

# Live Auto Recorder

CHZZK · YouTube 라이브 자동 녹화 도구

[![Docker pulls](https://img.shields.io/docker/pulls/yeowoonlee/live-auto-recorder?logo=docker&label=pulls)](https://hub.docker.com/r/yeowoonlee/live-auto-recorder)

</div>

CHZZK와 YouTube 라이브를 자동으로 감지해서 녹화하고, 웹 화면에서 상태와 녹화 파일을 관리할 수 있는 Docker 기반 도구입니다.

개인 서버나 홈서버에서 계속 켜 두고 사용하는 환경을 기준으로 만들었습니다.

## 주요 기능

- CHZZK / YouTube 라이브 자동 감지 및 녹화
- 채널별 자동 녹화 설정과 수동 시작/중지
- 화질, 파일 형식, 저장 경로 등 녹화 옵션 설정
- 제목·카테고리·요일·시간대 기반 채널별 녹화 규칙
- 녹화 상태, 시스템 사용량, 저장 공간을 웹에서 확인
- 녹화 중단이나 파일 정체 감지 및 제한된 자동 재연결
- 완료된 녹화 파일 검사와 필요 시 자동 복구 시도
- 재연결로 나뉜 세그먼트를 방송 단위로 묶어 확인하고 수동 병합
- 저장 공간 부족 시 신규 녹화 차단 및 안전한 정리 기능
- Telegram / Discord / Webhook 알림
- rclone을 이용한 외부 스토리지 보관
- 녹화 기록, 백업/복원, 시스템 점검 등 운영 기능

## 설치

Docker와 Docker Compose가 필요합니다.

```bash
git clone https://github.com/no-rahc/Live_auto_recorder.git
cd Live_auto_recorder
cp .env.example .env
mkdir -p data recordings logs tmp

docker compose pull
docker compose up -d
```

실행 후 아래 주소로 접속합니다.

```text
http://127.0.0.1:5000
```

기본 `compose.yaml`은 관리 화면을 `127.0.0.1`에만 공개하도록 되어 있습니다. 외부에서 접속할 필요가 있다면 포트를 직접 인터넷에 노출하기보다는 리버스 프록시나 VPN을 사용하는 것을 권장합니다.

## 기본 설정

주요 경로와 포트는 `.env`에서 변경할 수 있습니다.

| 변수 | 기본값 |
|---|---|
| `LIVE_AUTO_RECORDER_IMAGE` | `yeowoonlee/live-auto-recorder:latest` |
| `APP_PORT` | `5000` |
| `TZ` | `Asia/Seoul` |
| `CONFIG_PATH` | `./data` |
| `RECORDINGS_PATH` | `./recordings` |
| `LOG_PATH` | `./logs` |
| `TMP_PATH` | `./tmp` |

설정을 바꾼 뒤에는 컨테이너를 다시 생성합니다.

```bash
docker compose up -d --force-recreate
```

채널 등록, 쿠키, 녹화 옵션, 알림 같은 대부분의 설정은 웹 관리 화면에서도 변경할 수 있습니다.

## 업데이트

```bash
git pull --ff-only
docker compose pull
docker compose up -d --force-recreate
```

업데이트 전에는 `data` 디렉터리와 필요한 녹화 파일을 백업해 두는 것을 권장합니다.

## 저장되는 데이터

기본 구성에서는 다음 경로를 호스트에 보관합니다.

```text
data/        설정, SQLite 기록, 쿠키 및 운영 데이터
recordings/  녹화 파일
logs/        로그
/tmp/        임시 파일
```

특히 `data` 디렉터리는 설정과 녹화 기록이 들어 있으므로 정기적으로 백업하는 것이 좋습니다.

## 문서

세부 운영 기능과 내부 구조는 아래 문서에 정리되어 있습니다.

- [운영 가이드](docs/OPERATIONS.md)
- [프로젝트 구조](docs/ARCHITECTURE.md)
- [보안 안내](SECURITY.md)
- [기여 방법](CONTRIBUTING.md)
- [변경 내역](CHANGELOG.md)

## 라이선스

[MIT License](LICENSE)

저장소에 포함된 일부 폰트는 별도 라이선스를 따릅니다. 자세한 내용은 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)를 참고하세요.
