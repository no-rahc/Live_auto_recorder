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

## 대시보드 갱신 구조

실시간 시스템 지표는 기능 코드와 분리된 `system-metrics-v2.js`가 관리합니다.

- 녹화 현황 화면은 시스템 지표 WebSocket 연결을 하나만 유지합니다.
- 메인 화면에서 같은 시점에 발생하는 `/api/sys_metrics` 요청은 하나로 병합합니다.
- 브라우저 탭이 숨겨진 동안에는 최근 값을 재사용해 불필요한 네트워크 요청을 줄입니다.
- CPU·메모리·네트워크 그래프는 완만하게 보간하고 숫자 영역의 폭을 고정합니다.
- 디스크 카드는 매 갱신마다 삭제하지 않고 마운트 경로를 키로 사용해 기존 DOM을 갱신합니다.
- 동적으로 추가된 UI의 접근성 처리는 문서 전체가 아닌 새 요소만 묶어서 수행합니다.

따라서 2초 단위 갱신 중에도 카드 크기와 그리드 위치가 유지되며, 같은 데이터를 위한 중복 렌더링과 중복 요청이 줄어듭니다.

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
app_entry.py                            # Docker 진입점과 UI 정적 자산 주입
live_auto_recorder.py                   # FastAPI 애플리케이션과 API
module/                                 # 녹화·채널·알림·파일 관리 모듈
templates/                              # 기존 웹 UI 템플릿
templates/static/css/console-v2.css     # 공통 Console v2 디자인
templates/static/css/system-metrics-v2.css
templates/static/js/console-v2.js       # 내비게이션·테마·접근성
templates/static/js/system-metrics-v2.js # 실시간 지표 연결·캐시·안정화
compose.yaml                            # 운영용 Compose 구성
Dockerfile                              # 컨테이너 이미지 빌드 설정
```

`app_entry.py`의 UI 미들웨어는 대시보드 HTML 경로에만 적용됩니다. API, 정적 파일, WebSocket, 다운로드 요청은 응답 본문 가공 과정을 거치지 않습니다.

## 라이선스

MIT License. 자세한 내용은 [LICENSE](LICENSE)를 확인하세요.

## 면책사항

방송 녹화 및 재배포 시 CHZZK, YouTube 등 각 플랫폼의 이용약관과 저작권·초상권·개인정보 보호 관련 법률을 준수하세요.
