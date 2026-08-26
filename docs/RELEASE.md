# Release workflow

Live Auto Recorder는 루트의 `VERSION` 파일을 릴리스 버전의 단일 기준으로 사용합니다.

## 1. 일반 변경 커밋

커밋과 PR 제목은 Conventional Commits 형식을 사용합니다.

```text
feat(ui): improve recording dashboard
fix(docker): correct ytarchive download
refactor(core): simplify channel state handling
docs: reorganize deployment guide
ci: update GitHub Actions runtime
```

허용 형식:

```text
<type>(<scope>): <summary>
```

주요 type은 `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`입니다.

## 2. 릴리스 버전 준비

기본 버전 증가는 patch 단위입니다.

```bash
python scripts/release.py bump \
  --summary "녹화 현황 레이아웃을 개선했습니다." \
  --summary "배포 문서와 릴리스 절차를 정리했습니다."
```

위 명령은 다음 파일을 함께 갱신합니다.

- `VERSION`
- `CHANGELOG.md`

minor 또는 major 증가가 필요한 경우에만 명시적으로 지정합니다.

```bash
python scripts/release.py bump minor --summary "새 설정 백업 기능을 추가했습니다."
python scripts/release.py bump major --summary "설정 파일 형식을 변경했습니다."
```

## 3. 릴리스 메타데이터 검사

```bash
python scripts/release.py check
```

GitHub Actions와 Docker 게시 워크플로도 같은 검사를 실행하므로 버전이 어긋난 상태로 병합하거나 이미지를 게시할 수 없습니다.

## 4. 릴리스 커밋

기능 변경을 먼저 별도 커밋한 뒤, 버전 파일만 릴리스 커밋으로 분리하는 방식을 권장합니다.

```bash
git add VERSION CHANGELOG.md
git commit -m "chore(release): v1.1.5"
```

또는 작업 트리에 릴리스 파일 외 변경이 없을 때 다음 명령으로 커밋까지 만들 수 있습니다.

```bash
python scripts/release.py bump \
  --summary "변경 내용을 작성합니다." \
  --commit
```

## 5. PR과 병합

PR 제목도 Conventional Commits 형식을 사용합니다.

```text
feat(ui): refine light dashboard and release v1.1.5
```

검사가 모두 통과하면 squash merge합니다. 병합 후 Docker 게시 워크플로가 다음 태그를 생성합니다.

```text
no-rahc/live-auto-recorder:latest
no-rahc/live-auto-recorder:v1.1.5
```

## 권장 작업 순서

```text
기능 작업
→ Conventional Commit
→ scripts/release.py bump
→ release metadata check
→ PR
→ squash merge
→ Docker Hub latest + version tag 게시
```
