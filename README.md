<div align="center">

# Live Auto Recorder

**CHZZK · YouTube 라이브를 자동으로 감지하고 녹화하는 셀프호스팅 웹 애플리케이션**

채널 등록부터 실시간 녹화 상태, 시스템 사용량, 쿠키, 파일, 알림과 녹화 이력까지 하나의 웹 화면에서 관리합니다.

[![UI checks](https://img.shields.io/github/actions/workflow/status/no-rahc/Live_auto_recorder/ui-check.yml?branch=main&label=UI%20checks)](../../actions/workflows/ui-check.yml)
[![Docker publish](https://img.shields.io/github/actions/workflow/status/no-rahc/Live_auto_recorder/docker-publish.yml?branch=main&label=Docker%20publish)](../../actions/workflows/docker-publish.yml)
[![Docker pulls](https://img.shields.io/docker/pulls/no-rahc/live-auto-recorder?label=Docker%20pulls)](https://hub.docker.com/r/no-rahc/live-auto-recorder)
[![License](https://img.shields.io/github/license/no-rahc/Live_auto_recorder)](LICENSE)

[빠른 시작](#빠른-시작) · [업데이트](#업데이트) · [설정](#배포-설정) · [운영 확인](#운영-확인) · [문제 해결](#문제-해결)

</div>

---

## 주요 기능

| 영역 | 제공 기능 |
|---|---|
| 자동 녹화 | CHZZK·YouTube 라이브 감지, 예약 대기, 개별·전체 녹화 제어 |
| 웹 대시보드 | 현재 녹화 상태, CPU·메모리·네트워크·녹화 저장소 확인 |
| 채널 관리 | 채널 등록·수정·삭제, 녹화 활성화, 품질과 저장 경로 설정 |
| 운영 관리 | 쿠키, 애플리케이션 설정, 녹화 이력, 파일 관리 |
| 알림 | Telegram·Discord를 통한 녹화 이벤트 알림 |
| 저장소 | 로컬 디스크와 Docker bind mount를 통한 NAS/CIFS 경로 사용 |
| 배포 | Docker Compose, 상태 검사, 자동 재시작, 로그 순환, Docker Hub 이미지 |

Docker 이미지에는 `FFmpeg`, `yt-dlp`, `ytarchive`, `aria2`와 실행에 필요한 Python 패키지가 포함됩니다.

## 빠른 시작

### 요구 사항

- Docker Engine
- Docker Compose 플러그인
- 녹화 파일을 저장할 충분한 디스크 공간

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

### 3. 컨테이너 실행

```bash
docker compose pull
docker compose up -d
```

### 4. 웹 화면 접속

```text
http://서버주소:5000
```

기본 Docker 이미지는 다음과 같습니다.

```text
no-rahc/live-auto-recorder:latest
```

## 업데이트

설정과 녹화 파일은 호스트 볼륨에 남아 있으므로 컨테이너를 교체해도 유지됩니다.

```bash
git pull
docker compose pull
docker compose up -d --force-recreate
```

특정 버전을 고정해서 운영하려면 `.env`에서 이미지 태그를 변경합니다.

```env
LIVE_AUTO_RECORDER_IMAGE=no-rahc/live-auto-recorder:v1.1.5
```

`latest`는 최신 배포본을, `vX.Y.Z`는 고정 릴리스를 가리킵니다.

## 배포 설정

`.env`에서 포트와 호스트 저장 경로를 변경할 수 있습니다.

| 변수 | 기본값 | 용도 |
|---|---:|---|
| `LIVE_AUTO_RECORDER_IMAGE` | `no-rahc/live-auto-recorder:latest` | 실행할 Docker 이미지 |
| `APP_PORT` | `5000` | 외부에 공개할 웹 포트 |
| `TZ` | `Asia/Seoul` | 컨테이너 시간대 |
| `LOG_LEVEL` | `info` | 애플리케이션 로그 수준 |
| `CONFIG_PATH` | `./data` | 설정, 계정, 쿠키 등 영구 데이터 |
| `RECORDINGS_PATH` | `./recordings` | 녹화 파일 저장 위치 |
| `LOG_PATH` | `./logs` | 로그 저장 위치 |
| `TMP_PATH` | `./tmp` | 임시 작업 파일 위치 |

### NAS 또는 별도 디스크 사용

상대 경로 대신 호스트의 절대 경로를 지정할 수 있습니다.

```env
CONFIG_PATH=/srv/live-auto-recorder/data
RECORDINGS_PATH=/mnt/nas/recordings
LOG_PATH=/srv/live-auto-recorder/logs
TMP_PATH=/srv/live-auto-recorder/tmp
```

Docker가 해당 경로를 읽고 쓸 수 있도록 호스트의 마운트 상태와 권한을 먼저 확인하세요.

### 다른 포트 사용

```env
APP_PORT=8080
```

변경 후 컨테이너를 다시 생성합니다.

```bash
docker compose up -d --force-recreate
```

## 데이터 구조

| 호스트 기본 경로 | 컨테이너 경로 | 내용 |
|---|---|---|
| `./data` | `/app/json` | 설정, 채널, 계정, 쿠키 및 상태 데이터 |
| `./recordings` | `/app/chzzk` | 녹화 결과 파일 |
| `./logs` | `/app/logs` | 애플리케이션 로그 |
| `./tmp` | `/app/tmp` | 임시 다운로드와 처리 파일 |

백업 시 최소한 `data`와 `recordings` 경로를 함께 보관하는 것을 권장합니다.

## 운영 확인

### 컨테이너 상태

```bash
docker compose ps
```

정상 상태에서는 `live-auto-recorder` 컨테이너가 실행 중이며 health 상태가 `healthy`로 표시됩니다.

### 실시간 로그

```bash
docker compose logs -f recorder
```

최근 로그만 확인하려면 다음과 같이 실행합니다.

```bash
docker compose logs --tail 200 recorder
```

### 재시작

```bash
docker compose restart recorder
```

Compose 구성에는 다음 운영 설정이 포함되어 있습니다.

- 비정상 종료 후 자동 재시작
- 30초 간격 HTTP health check
- 45초 종료 유예 시간
- JSON 로그 파일당 10MB, 최대 5개 순환
- `tini`를 통한 프로세스·시그널 정리

## 로컬 개발 실행

Docker가 아닌 로컬 Python 환경에서 확인할 때도 `app_entry.py`를 진입점으로 사용합니다.

```bash
python -m pip install -r requirements.txt
python app_entry.py
```

기본 접속 주소는 `http://127.0.0.1:5000`입니다.

## Docker Hub 자동 게시

`main`에 병합되면 GitHub Actions가 이미지를 빌드하고 다음 태그를 Docker Hub에 게시합니다.

```text
no-rahc/live-auto-recorder:latest
no-rahc/live-auto-recorder:vX.Y.Z
```

저장소 설정에 다음 Actions secret이 필요합니다.

| Secret | 값 |
|---|---|
| `DOCKERHUB_USERNAME` | Docker Hub 사용자명 |
| `DOCKERHUB_TOKEN` | Read & Write 권한의 Docker Hub Access Token |

Docker 게시 전에 릴리스 메타데이터 일치 여부, Docker 빌드, SBOM과 provenance 생성을 함께 수행합니다.

## 릴리스와 커밋 규칙

릴리스 버전은 루트의 `VERSION` 파일을 단일 기준으로 사용하며 기본적으로 patch 단위로 증가합니다.

```bash
python scripts/release.py bump \
  --summary "변경 내용을 작성합니다."
```

검사 명령:

```bash
python scripts/release.py check
```

커밋과 PR 제목은 다음 형식을 사용합니다.

```text
feat(ui): improve recording dashboard
fix(docker): correct image build
chore(release): v1.1.5
```

자세한 절차는 [`docs/RELEASE.md`](docs/RELEASE.md)를 확인하세요.

## 문제 해결

<details>
<summary><strong>웹 화면에 접속할 수 없습니다.</strong></summary>

1. 컨테이너 상태를 확인합니다.

   ```bash
   docker compose ps
   ```

2. 시작 로그를 확인합니다.

   ```bash
   docker compose logs --tail 200 recorder
   ```

3. `.env`의 `APP_PORT`와 서버 방화벽 설정을 확인합니다.

</details>

<details>
<summary><strong>업데이트했는데 이전 화면이 보입니다.</strong></summary>

최신 이미지를 다시 받고 컨테이너를 강제로 교체합니다.

```bash
docker compose pull
docker compose up -d --force-recreate
```

이후 브라우저에서 강력 새로고침을 실행합니다.

```text
Ctrl + Shift + R
```

</details>

<details>
<summary><strong>녹화 저장소 용량이 잘못 표시됩니다.</strong></summary>

`.env`의 `RECORDINGS_PATH`가 실제 녹화 디스크 또는 NAS 마운트 경로를 가리키는지 확인합니다. 컨테이너 내부에서는 해당 경로가 `/app/chzzk`로 연결됩니다.

</details>

<details>
<summary><strong>NAS에 파일을 쓸 수 없습니다.</strong></summary>

NAS가 호스트에 먼저 마운트되어 있어야 하며 Docker 프로세스에 쓰기 권한이 있어야 합니다. Compose 실행 전 다음을 확인하세요.

```bash
mount | grep -E 'cifs|nfs'
touch /mnt/nas/recordings/.write-test
rm /mnt/nas/recordings/.write-test
```

</details>

## 보안 안내

- `data` 디렉터리에는 계정·쿠키·알림 인증정보가 포함될 수 있으므로 공개 저장소에 커밋하지 마세요.
- 인터넷에 직접 공개할 경우 로그인 모드를 활성화하고 HTTPS 리버스 프록시 사용을 권장합니다.
- Docker Hub 토큰과 서비스 인증정보를 README, 이슈 또는 로그에 붙여 넣지 마세요.

## 라이선스와 이용 책임

이 프로젝트는 [MIT License](LICENSE)로 배포됩니다.

방송 녹화와 저장·재배포 시 CHZZK, YouTube 등 각 플랫폼의 이용약관과 저작권·초상권·개인정보 보호 관련 법률을 준수해야 합니다. 프로젝트 사용으로 발생하는 법적·운영상 책임은 사용자에게 있습니다.
