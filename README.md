<div align="center">

# Live Auto Recorder

**CHZZK · YouTube 라이브 방송을 자동 감지하고 안전하게 녹화하는 셀프호스팅 웹 애플리케이션**

채널 등록, 실시간 녹화 제어, 저장소 보호, 자동 복구, 후처리, 백업, 통계와 파일 관리를 하나의 웹 콘솔에서 운영합니다.

[![UI checks](https://img.shields.io/github/actions/workflow/status/no-rahc/Live_auto_recorder/ui-check.yml?branch=main&label=UI%20checks)](../../actions/workflows/ui-check.yml)
[![Core checks](https://img.shields.io/github/actions/workflow/status/no-rahc/Live_auto_recorder/core-check.yml?branch=main&label=Core%20checks)](../../actions/workflows/core-check.yml)
[![Docker publish](https://img.shields.io/github/actions/workflow/status/no-rahc/Live_auto_recorder/docker-publish.yml?branch=main&label=Docker%20publish)](../../actions/workflows/docker-publish.yml)
[![Docker pulls](https://img.shields.io/docker/pulls/no-rahc/live-auto-recorder?label=Docker%20pulls)](https://hub.docker.com/r/no-rahc/live-auto-recorder)
[![License](https://img.shields.io/github/license/no-rahc/Live_auto_recorder)](LICENSE)

[빠른 시작](#빠른-시작) · [운영 관리](#운영-관리) · [업데이트](#업데이트) · [배포 설정](#배포-설정) · [문제 해결](#문제-해결)

</div>

---

## 주요 기능

| 영역 | 제공 기능 |
|---|---|
| 자동 녹화 | CHZZK·YouTube 라이브 탐지, 예약 대기, 개별·전체 녹화 제어 |
| 녹화 안전성 | 파일 증가 감시, 멈춤 탐지, 자동 재연결, 최대 녹화 시간 |
| 저장소 보호 | 여유 공간 경고, 신규 녹화 차단, 삭제 미리보기, 안전한 자동 정리 |
| 채널 규칙 | 제목·카테고리·요일·시간대·지연·화질·최소/최대 길이 정책 |
| 운영 관리 | 후처리 작업, 설정 백업·복원, 감사 기록, 녹화 통계와 CSV |
| 웹 콘솔 | 반응형 라이트 UI, 채널·쿠키·파일·녹화 이력 관리 |
| 알림 | Telegram·Discord 저장소 경고와 자동 복구 알림 |
| 배포 | Docker Compose, health check, 로그 순환, AMD64·ARM64 이미지 |

Docker 이미지에는 `FFmpeg`, `yt-dlp`, `ytarchive`, `aria2`와 실행에 필요한 Python 패키지가 포함됩니다.

## 빠른 시작

### 요구 사항

- Docker Engine
- Docker Compose 플러그인
- 녹화 파일을 저장할 디스크 또는 NAS 경로

### 1. 저장소 받기

```bash
git clone https://github.com/no-rahc/Live_auto_recorder.git
cd Live_auto_recorder
```

### 2. 배포 설정 만들기

```bash
cp .env.example .env
mkdir -p data recordings logs tmp
```

### 3. 실행

```bash
docker compose pull
docker compose up -d
```

### 4. 접속

```text
http://서버주소:5000
```

기본 이미지는 `no-rahc/live-auto-recorder:latest`이며 `linux/amd64`와 `linux/arm64`를 지원합니다.

## 운영 관리

사이드바의 **운영 관리**에서 다음 기능을 사용할 수 있습니다.

- 녹화 저장소의 남은 공간과 녹화 차단 상태 확인
- 보관 기간·최대 용량·목표 여유 공간 기준 삭제 미리보기
- 녹화 중 파일과 최근 생성 파일을 제외한 안전한 정리
- 채널별 기록 속도, 파일 크기, 마지막 기록 시각과 재연결 횟수 확인
- 멈춘 녹화의 제한된 자동 재연결
- 후처리 작업 상태, 취소와 재시도
- 설정·채널 백업, 선택적 민감정보 포함, 복원 전 자동 안전 백업
- 최근 14일·채널별 녹화 통계와 CSV 내려받기
- 채널별 자동 녹화 규칙과 작업 감사 기록

기본 보호 정책은 남은 공간 10%에서 경고하고 5% 이하에서 **신규 녹화를 차단**합니다. 자동 파일 삭제는 기본적으로 꺼져 있으며 운영 관리 화면에서 명시적으로 켜야 합니다.

자세한 동작과 안전 기준은 [`docs/OPERATIONS.md`](docs/OPERATIONS.md)를 확인하세요.

## 업데이트

설정과 녹화 파일은 호스트 볼륨에 유지됩니다.

```bash
git pull
docker compose pull
docker compose up -d --force-recreate
```

특정 버전을 고정하려면 `.env`를 수정합니다.

```env
LIVE_AUTO_RECORDER_IMAGE=no-rahc/live-auto-recorder:v1.1.6
```

`latest`는 최신 배포본, `vX.Y.Z`는 고정 릴리스입니다.

## 배포 설정

| 변수 | 기본값 | 용도 |
|---|---:|---|
| `LIVE_AUTO_RECORDER_IMAGE` | `no-rahc/live-auto-recorder:latest` | 실행할 Docker 이미지 |
| `APP_PORT` | `5000` | 외부 웹 포트 |
| `TZ` | `Asia/Seoul` | 컨테이너 시간대 |
| `LOG_LEVEL` | `info` | 애플리케이션 로그 수준 |
| `CONFIG_PATH` | `./data` | 설정, 계정, 쿠키, 운영 정책과 백업 |
| `RECORDINGS_PATH` | `./recordings` | 녹화 파일 저장 위치 |
| `LOG_PATH` | `./logs` | 로그 저장 위치 |
| `TMP_PATH` | `./tmp` | 임시 작업 파일 위치 |

### NAS 또는 별도 디스크

```env
CONFIG_PATH=/srv/live-auto-recorder/data
RECORDINGS_PATH=/mnt/nas/recordings
LOG_PATH=/srv/live-auto-recorder/logs
TMP_PATH=/srv/live-auto-recorder/tmp
```

NAS는 Docker 실행 전에 호스트에 마운트되어 있어야 하고 Docker 프로세스가 읽고 쓸 수 있어야 합니다.

### 다른 포트

```env
APP_PORT=8080
```

변경 후 다시 생성합니다.

```bash
docker compose up -d --force-recreate
```

## 데이터 구조

| 호스트 기본 경로 | 컨테이너 경로 | 내용 |
|---|---|---|
| `./data` | `/app/json` | 설정, 채널, 계정, 쿠키, 운영 정책, 작업 이력, 백업 |
| `./recordings` | `/app/chzzk` | 녹화 결과 파일 |
| `./logs` | `/app/logs` | 애플리케이션 로그 |
| `./tmp` | `/app/tmp` | 임시 다운로드와 처리 파일 |

최소한 `data`와 `recordings`를 함께 백업하세요.

## 운영 확인

```bash
# 컨테이너와 health 상태
docker compose ps

# 최근 로그
docker compose logs --tail 200 recorder

# 실시간 로그
docker compose logs -f recorder

# 재시작
docker compose restart recorder
```

Compose 구성에는 비정상 종료 후 자동 재시작, 30초 HTTP health check, 45초 종료 유예, JSON 로그 순환과 `tini` 프로세스 정리가 포함됩니다.

## 로컬 개발 실행

`VERSION`을 포함한 전체 확장 기능이 적용되도록 반드시 `app_entry.py`를 사용합니다.

```bash
python -m pip install -r requirements.txt
python app_entry.py
```

기본 주소는 `http://127.0.0.1:5000`입니다.

### 검사

```bash
python -m unittest discover -s tests -p 'test_operations_v2.py' -v
npm install
npm run test:ui
python scripts/release.py check
```

## Docker Hub 자동 게시

`main`에 병합하면 GitHub Actions가 AMD64·ARM64 이미지를 빌드하고 다음 태그를 게시합니다.

```text
no-rahc/live-auto-recorder:latest
no-rahc/live-auto-recorder:vX.Y.Z
```

필요한 Actions secret:

| Secret | 값 |
|---|---|
| `DOCKERHUB_USERNAME` | Docker Hub 사용자명 |
| `DOCKERHUB_TOKEN` | Read & Write 권한의 Docker Hub Access Token |

## 릴리스와 커밋 규칙

버전은 루트 `VERSION`을 기준으로 기본 patch 단위로 올립니다.

```bash
python scripts/release.py bump \
  --summary "변경 내용을 작성합니다."
python scripts/release.py check
```

커밋과 PR 제목 예시:

```text
feat(operations): add recording safety center
fix(storage): protect active recording files
chore(release): v1.1.6
```

자세한 절차는 [`docs/RELEASE.md`](docs/RELEASE.md)를 확인하세요.

## 문제 해결

<details>
<summary><strong>업데이트 후 이전 화면이 보입니다.</strong></summary>

```bash
docker compose pull
docker compose up -d --force-recreate
```

그다음 브라우저에서 `Ctrl + Shift + R`을 실행합니다.
</details>

<details>
<summary><strong>저장소가 위험 또는 녹화 차단으로 표시됩니다.</strong></summary>

운영 관리에서 실제 녹화 경로와 남은 공간을 확인합니다. 자동 삭제를 켜기 전 반드시 **삭제 대상 미리보기**를 실행하세요. 녹화 중 파일과 최근 생성 파일은 정리 대상에서 자동 제외됩니다.
</details>

<details>
<summary><strong>NAS 용량이 잘못 표시되거나 쓸 수 없습니다.</strong></summary>

`.env`의 `RECORDINGS_PATH`가 실제 NAS 마운트를 가리키는지 확인합니다.

```bash
mount | grep -E 'cifs|nfs'
touch /mnt/nas/recordings/.write-test
rm /mnt/nas/recordings/.write-test
```
</details>

<details>
<summary><strong>로그인이 잠겼습니다.</strong></summary>

같은 IP에서 10분 동안 5회 실패하면 추가 로그인이 일시 차단됩니다. 10분 후 다시 시도하고, 리버스 프록시를 사용한다면 실제 클라이언트 IP가 `X-Forwarded-For`로 전달되는지 확인하세요.
</details>

## 보안 안내

- `data`에는 계정·쿠키·알림 인증정보와 백업이 포함될 수 있으므로 공개 저장소에 커밋하지 마세요.
- 민감정보 포함 백업은 필요할 때만 생성하고 접근 권한을 제한하세요.
- 인터넷에 공개할 때는 로그인 모드와 HTTPS 리버스 프록시를 사용하세요.
- Docker Hub 토큰과 서비스 인증정보를 이슈·로그·채팅에 붙여 넣지 마세요.

## 라이선스와 이용 책임

이 프로젝트는 [MIT License](LICENSE)로 배포됩니다.

방송 녹화와 저장·재배포 시 CHZZK, YouTube 등 각 플랫폼의 이용약관과 저작권·초상권·개인정보 보호 관련 법률을 준수해야 합니다. 프로젝트 사용으로 발생하는 법적·운영상 책임은 사용자에게 있습니다.
