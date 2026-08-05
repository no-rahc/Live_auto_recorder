# Live Auto Recorder

CHZZK 라이브 방송을 자동으로 감지하고 녹화하는 개인 서버용 대시보드 및 자동화 서비스입니다.

## 주요 기능

- 라이브 방송 자동 감지 및 녹화
- 실시간 녹화 상태와 시스템 리소스 대시보드
- 채널·쿠키·파일·백업·녹화 이력 관리
- Telegram 및 Discord 알림 선택 지원
- CIFS 기반 녹화 저장소 지원
- Docker 배포 및 healthcheck 지원
- 로그 로테이션을 포함한 운영 환경 구성
- 반응형 라이트 테마 대시보드

## 빠른 시작

```bash
docker compose build
docker compose up -d
```

애플리케이션은 설정과 인증정보를 별도의 runtime 볼륨으로 마운트하는 방식으로 동작합니다. 기본 설정 파일을 준비한 뒤 웹 UI 또는 runtime JSON 볼륨을 통해 채널과 알림 설정을 구성하세요.

## 설정 시 주의사항

다음 정보는 이 저장소에 포함하지 마세요.

- CHZZK 채널 ID와 개인 채널 설정
- 녹화 경로 및 CIFS 마운트 정보
- Telegram 봇 토큰과 채팅방 ID
- Discord 웹훅 URL
- OAuth 토큰 및 client secret
- 호스트명, 사설 IP, 사용자별 경로

runtime 상태와 비밀값은 `json/`, `.env`, 쿠키·토큰 파일 등으로 별도 관리하며, `.gitignore`에 의해 Git 추적에서 제외됩니다.

## 프로젝트 구조

```text
live_auto_recorder.py  # 애플리케이션 진입점
module/                # 녹화·채널·알림·파일 관리 모듈
templates/             # 웹 UI 템플릿과 정적 리소스
Dockerfile             # 컨테이너 이미지 빌드 설정
requirements.txt       # Python 의존성
```

## 라이선스

MIT License. 자세한 내용은 [LICENSE](LICENSE)를 확인하세요.

## 면책사항

이 프로젝트는 개인 서버에서 사용하는 독립적인 도구입니다. 방송 녹화 및 재배포 시 CHZZK, YouTube 등 각 플랫폼의 이용약관과 저작권·초상권·개인정보 보호 관련 법률을 반드시 준수하세요.
