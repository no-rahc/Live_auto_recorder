# Live Auto Recorder

CHZZK와 YouTube 라이브 방송을 자동 감지·녹화하고 웹에서 상태, 채널, 설정, 쿠키, 파일과 녹화 이력을 관리하는 셀프호스팅 서비스입니다.

## 주요 기능

- 라이브 채널 자동 감지 및 녹화
- 반응형 관제 대시보드와 실시간 시스템 지표
- 채널·쿠키·파일·녹화 이력 관리
- Telegram 및 Discord 알림
- CIFS/NAS 녹화 저장소 지원
- 라이트/다크 테마와 모바일 내비게이션
- Docker Compose 및 Docker Hub 자동 배포 구성

## Docker로 실행

```bash
cp .env.example .env
mkdir -p data recordings logs tmp
docker compose pull
docker compose up -d
```

브라우저에서 `http://서버주소:5000`으로 접속합니다.

기본 이미지는 `no-rahc/live-auto-recorder:latest`입니다. Docker Hub 네임스페이스가 다르면 `.env`의 `LIVE_AUTO_RECORDER_IMAGE`를 변경하세요. 아직 이미지가 게시되지 않았다면 다음 명령으로 로컬 빌드할 수 있습니다.

```bash
docker compose up -d --build
```

### 주요 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `APP_PORT` | `5000` | 호스트에 공개할 웹 포트 |
| `TZ` | `Asia/Seoul` | 컨테이너 시간대 |
| `CONFIG_PATH` | `./data` | 설정과 인증정보 저장 경로 |
| `RECORDINGS_PATH` | `./recordings` | 녹화 파일 저장 경로 |
| `LOG_PATH` | `./logs` | 로그 저장 경로 |
| `TMP_PATH` | `./tmp` | 임시 작업 경로 |

설정과 쿠키 등 민감한 런타임 데이터는 저장소에 커밋하지 말고 위 볼륨 경로에 보관하세요.

## Docker Hub 자동 게시

`.github/workflows/docker-publish.yml`은 `main` 브랜치 또는 `v*` 태그가 푸시될 때 이미지를 빌드하고 Docker Hub로 게시합니다.

저장소의 **Settings → Secrets and variables → Actions**에 다음 Repository secret을 추가하세요.

- `DOCKERHUB_USERNAME`: Docker Hub 사용자명
- `DOCKERHUB_TOKEN`: Docker Hub Access Token

Docker Hub에서 `live-auto-recorder` 저장소를 먼저 만든 뒤 PR을 병합하면 `latest` 이미지가 게시됩니다. 버전 태그를 푸시하면 동일한 버전 태그 이미지도 생성됩니다.

## 로컬 Python 실행

```bash
python -m pip install -r requirements.txt
python app_entry.py
```

## 프로젝트 구조

```text
app_entry.py                       # Docker/서버용 실행 진입점과 UI 레이어
live_auto_recorder.py              # FastAPI 애플리케이션과 API
module/                            # 녹화·채널·알림·파일 관리 모듈
templates/                         # 기존 웹 UI 템플릿과 정적 리소스
templates/static/css/console-v2.css
templates/static/js/console-v2.js
compose.yaml                       # 운영용 Compose 구성
Dockerfile                         # 컨테이너 이미지 빌드 설정
```

## 라이선스

MIT License. 자세한 내용은 [LICENSE](LICENSE)를 확인하세요.

## 면책사항

방송 녹화 및 재배포 시 CHZZK, YouTube 등 각 플랫폼의 이용약관과 저작권·초상권·개인정보 보호 관련 법률을 준수하세요.
