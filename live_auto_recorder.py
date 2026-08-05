from module.log_setup import setup_logging, get_logger
setup_logging()
logger = get_logger("Live Auto Recorder")
import subprocess
import os
import time
import traceback
import json
import sys
import ctypes
import asyncio
import platform
import threading
import webbrowser
import re
import string
import shutil
import secrets
from datetime import datetime
from typing import Optional, Any, List, Dict

from module.recording_history import get_history, get_stats as get_recording_stats

sys.stdout.reconfigure(encoding='utf-8')

# 필요한 모듈을 설치하는 함수
def install_missing_modules():
    # 윈도우 외  pygetwindow를 설치하지 않도록 분기처리
    if os.name == 'nt':
        missing_modules = [
            "requests", "httpx", "fastapi", "uvicorn", "aiohttp",
            "jinja2", "werkzeug", "itsdangerous", "python-multipart",
            "starlette", "psutil", "cryptography", "pystray", "pillow",
            "py-cpuinfo"
            
        ]
    else:
        missing_modules = [
            "requests", "httpx", "fastapi", "uvicorn", "aiohttp",
            "jinja2", "werkzeug", "itsdangerous", "python-multipart",
            "starlette", "psutil", "cryptography", "pystray", "pillow",
            "py-cpuinfo"
        ]

    installed_modules = []

    # 각 모듈이 이미 설치되어 있는지 확인하고, 없는 경우 설치 목록에 추가
    for module in missing_modules:
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "show", module],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except subprocess.CalledProcessError:
            installed_modules.append(module)

    # 설치가 필요한 모듈이 있는 경우 설치 진행
    if installed_modules:
        logger.info("필수 모듈을 자동으로 설치합니다...")
        for module in installed_modules:
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", module])
                logger.info(f"'{module}' 모듈 설치 완료.")
            except subprocess.CalledProcessError as e:
                logger.info(f"모듈 설치 중 오류 발생: {e}")

        logger.info("필수 모듈 설치가 완료되었습니다.")
    else:
        logger.info("모든 필수 모듈이 이미 설치되어 있습니다.")

install_missing_modules()

import uvicorn
import requests
import httpx
import psutil


try:
    import cpuinfo
    import pystray
    from PIL import Image

except Exception:
    pystray = None
    Image = None
    cpuinfo = None

from fastapi import FastAPI, Request, Form, HTTPException, BackgroundTasks, Depends, Body, Query, APIRouter
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from werkzeug.security import generate_password_hash, check_password_hash
from contextlib import asynccontextmanager, suppress

from module.data_manager import (
    RecorderManager, loadAccount, saveAccount, loadCookies, saveCookies,
    loadChannels, saveChannels, loadConfig, saveConfig, yloadCookies,
    saveTelegram, loadTelegram, sendTelegram, last_notified_state,
    CONFIG_PATH, CHANNELS_PATH, COOKIE_PATH, LOGIN_PATH, getFFmpeg, 
    getStreamlink, getYtarchive, getBaseUrl, toBool
)

from module.meta_cache import (
    ensure as mc_ensure, refreshLoop as mc_refreshLoop, 
    getMetadataCached, getThumbnailsCached
)

from module.file_manager import (
    buildAllowedRoots, ensureInRoots, listDir, diskUsageFor, listDisks,
    makeTrashPath, softDelete, hardDelete, movePath, renamePath, mkdirPath,
    busyFilePaths, isLocked, normPath, listMountRoots, streamCopyFile
)

from module.recording_adapter import fetchMetadata, startSession
from module.channel_fsm import ChannelFsm
from module.live_recorder import queueBatchLast, queueBatchPattern

PROGRAM_NAME = "Live Auto Recorder"
PROGRAM_VERSION = "v1.1.3"

# 현재 파일의 경로
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 정적 파일 경로와 템플릿 디렉토리 설정
static_directory = os.path.join(BASE_DIR, "templates", "static")
templates_directory = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=templates_directory)
templates.env.globals.update(program_version=PROGRAM_VERSION)

# data_manager.py의 RecorderManager 클래스 인스턴스 생성
recorder_manager = RecorderManager()

# 네트워크 속도 계산을 위한 직전 스냅샷 저장소 (프로세스 메모리)
_last_net: Dict[str, float] = {"ts": 0.0, "bytes_sent": 0.0, "bytes_recv": 0.0}

# CPU 명칭 조회
_CPU_NAME = None


# 애플리케이션 생애주기 핸들러
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.channels = loadChannels()
    app.state.fsm = ChannelFsm()
    app.state.channels_lock = asyncio.Lock()
    app.state.config = loadConfig()
    app.state.chzzk_cookies = loadCookies()
    app.state.youtube_cookie_path = yloadCookies()
    app.state.bg_tasks = set()

    changed = False
    async with app.state.channels_lock:
        changed = coerceChannelsInplace(app.state.channels)
    if changed:
        await asyncio.to_thread(saveChannels, app.state.channels)
    logger.info("채널 데이터 보정 적용 완료.")

    RecorderManager.setChannels(app.state.channels)
    RecorderManager.setChannelsRef(app.state.channels)
    RecorderManager.setChannelsLockRef(app.state.channels_lock)

    meta_task = None

    try:
        await initChannelStates(app)

        app.state.meta_fetcher = _makeMetaFetcher(app)
        app.state.save_debounced = DebouncedSaver(app, delay=1.2)
        mc_ensure(app)

        # 부팅 직후 1회성 메타 시드
        seed_task = asyncio.create_task(_seedMetadataWEB(app))

        meta_task = asyncio.create_task(
            mc_refreshLoop(app, app.state.meta_fetcher, app.state.save_debounced, app.state.channels_lock)
        )

        # 부팅시 한 번만 자동 시작 (Auto ON일 때)
        if app.state.config.get("autoRecordingMode", False):
            logger.debug("자동 녹화 모드: 부팅시 한 번만 WATCHING 진입")
            await app.state.fsm.startAllWatching()

        # CIFS 마운트 워치독 시작
        from module.cifs_watchdog import start_cifs_watchdog
        cifs_wd = start_cifs_watchdog()

        yield

    finally:

        # CIFS 워치독 정리
        try:
            from module.cifs_watchdog import stop_cifs_watchdog
            await stop_cifs_watchdog()
        except Exception:
            pass

        # 메타 루프 정리
        if meta_task and not meta_task.done():
            meta_task.cancel()
            with suppress(Exception):
                await meta_task

        # 시드 태스크 정리
        try:
            seed_task  # 존재하면 NameError 아님
            if seed_task and not seed_task.done():
                seed_task.cancel()
                with suppress(Exception):
                    await seed_task

        except NameError:
            pass

        # 백그라운드 태스크 모두 취소/대기
        try:
            pending = list(app.state.bg_tasks)
            for t in pending:
                t.cancel()
            for t in pending:
                with suppress(Exception):
                    await t
        except Exception as e:
            logger.warning(f"bg_tasks cleanup error: {e}")

        # 종료 직전 채널 저장 강제 플러시
        try:
            if hasattr(app.state, "save_debounced") and app.state.save_debounced:
                await app.state.save_debounced.flush()
        except Exception as e:
            logger.warning(f"save_debounced.flush failed: {e}")

        # httpx AsyncClient 정리 
        try:
            from module.live_recorder import closeHttpxClient
            await closeHttpxClient()
        except Exception as e:
            logger.warning(f"closeHttpxClient 실패(무시): {e}")


app = FastAPI(lifespan=lifespan)


if os.path.isdir(static_directory):
    app.mount("/static", StaticFiles(directory=static_directory), name="static")
else:
    logger.warning(f"Static dir not found: {static_directory}")


# 프로그램 첫 실행 시 FFmpeg, Streamlink, ytarchive 경로 확인
def checkRequiredPaths():
    ffmpeg_path = getFFmpeg()  # FFmpeg 경로 확인
    streamlink_path = getStreamlink()  # Streamlink 경로 확인
    ytarchive_path = getYtarchive()  # ytarchive 경로 확인

    # 각 프로그램 경로가 제대로 설정되지 않았을 경우 오류 처리
    if not ffmpeg_path:
        logger.error("FFmpeg 경로가 설정되지 않았습니다. 프로그램을 종료합니다.")
    elif not streamlink_path:
        logger.error("Streamlink 경로가 설정되지 않았습니다. 프로그램을 종료합니다.")
    elif not ytarchive_path:
        logger.error("ytarchive 경로가 설정되지 않았습니다. 프로그램을 종료합니다.")
    else:
        logger.info("필수 프로그램 경로 확인 완료.")
        return  # 모든 경로가 확인되었을 때 프로그램 계속 실행


# Windows 콘솔 창 최소화
def minimizeConsole():

    if os.name != "nt":
        return

    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if not hwnd:
            return  # pythonw.exe 등 콘솔이 없으면 무시
        SW_MINIMIZE = 6
        ctypes.windll.user32.ShowWindow(hwnd, SW_MINIMIZE)

    except Exception as e:
        logger.warning(f"콘솔 최소화 실패: {e}")


# 서버 기준 불리언 보정
def coerceChannelsInplace(chs: list):
    changed = False
    for ch in chs:
        # recordWatchParty 문자열 → 불리언
        if "recordWatchParty" in ch and not isinstance(ch["recordWatchParty"], bool):
            ch["recordWatchParty"] = toBool(ch["recordWatchParty"])
            changed = True

        # 유튜브는 recordWatchParty 강제 False
        if ch.get("platform") == "youtube" and ch.get("recordWatchParty", False):
            ch["recordWatchParty"] = False
            changed = True

        # 유튜브 확장자 강제 .mp4 
        if ch.get("platform") == "youtube" and ch.get("extension") != ".mp4":
            ch["extension"] = ".mp4"
            changed = True

        # extension 앞에 점 없으면 보정 
        ext = ch.get("extension")
        if isinstance(ext, str) and ext and not ext.startswith("."):
            ch["extension"] = f".{ext}"
            changed = True

        # record_enabled 불리언으로 보정
        if "record_enabled" in ch and not isinstance(ch["record_enabled"], bool):
            ch["record_enabled"] = toBool(ch["record_enabled"])
            changed = True

    return changed


# 상태 조회 헬퍼(읽기 전용)
def _getRecFilename(cid: str):
    try:
        return RecorderManager.recording_filename.get(cid)
    except Exception:
        return None


def _getRecStartTime(cid: str):
    try:
        ts = RecorderManager.recording_start_time.get(cid)
        return datetime.fromtimestamp(float(ts)) if ts else None
    except Exception:
        return None

# 전역 락 선언
thread_lock = threading.Lock()  # 동기 함수에서 사용할 락


# 메타데이터 가져오는 fetcher를 app에 바인딩하기 위한 팩토리
def _makeMetaFetcher(app: FastAPI):
    async def _fetch(channel: dict):
        platform = (channel.get('platform') or '').lower()
        return await fetchMetadata(channel, platform)
    return _fetch


# 세션을 사용하기 위한 미들웨어
account_data = loadAccount()
if account_data and 'secret_key' in account_data:
    app.add_middleware(SessionMiddleware, secret_key=account_data['secret_key'])
else:
    # secret_key가 없으면 기본적으로 생성
    new_secret_key = secrets.token_hex(32)
    saveAccount({'secret_key': new_secret_key})
    app.add_middleware(SessionMiddleware, secret_key=new_secret_key)


# 예외 처리기 정의
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        return RedirectResponse(url='/login')
    else:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )


# 채널 상태 초기화 함수
async def initChannelStates(app: FastAPI):
    try:
        logger.debug("initChannelStates 시작")
        async with app.state.channels_lock:
            for channel in app.state.channels:
                channel.setdefault('status', '대기 중')
                channel.setdefault('record_enabled', True)
                channel['live_title'] = "불러오는 중..."
                channel['category'] = "불러오는 중..."
                channel['thumbnail_url'] = (
                    '/static/img/youtube_thumbnail.png' if channel.get('platform') == 'youtube'
                    else '/static/img/default_thumbnail.png'
                )
        logger.debug("initChannelStates 완료")
    except Exception as e:
        logger.error(f"initChannelStates 중 오류 발생: {e}")
        raise


# 로그인 인증 의존성 함수 정의
async def requireLogin(request: Request):
    if not request.app.state.config.get('loginMode', False):
        return True
    if request.session.get('logged_in'):
        return True
    # API엔 401 JSON
    if request.url.path.startswith('/api/') or 'application/json' in (request.headers.get('accept','')):
        raise HTTPException(status_code=401, detail="Login required")
    return RedirectResponse(url="/login", status_code=302)


# 자동 녹화 모드 함수
async def autoRecording(app: FastAPI):
    cfg = app.state.config
    if app.state.config.get("autoRecordingMode", False):
        logger.debug("자동 녹화 모드 활성화 → 모든 채널 WATCHING 진입")
        asyncio.create_task(app.state.fsm.startAllWatching())
    else:
        logger.debug("자동 녹화 모드가 비활성화되어 있습니다.")


# 특정 채널의 녹화를 시작하는 함수
async def startRecordingForChannel(app, channel_id: str, is_user_request: bool = False):
    async with app.state.channels_lock:
        channels = list(app.state.channels)
    ch = next((c for c in channels if c.get("id") == channel_id), None)
    if not ch:
        return {"status": "error", "message": "unknown channel"}

    from module.data_manager import RecorderManager
    rm = RecorderManager()

    # 0) 이전 세션 잔재 선제 정리(이전 파일명/시간이 UI에 비치지 않도록)
    rm.recording_remove_start_time(channel_id)
    rm.recording_remove_filename(channel_id)
    rm.clear_tasks_process(channel_id)
    rm.set_status_recording(channel_id, False)

    # 1) 사용자 시작 의사 표시 및 예약 표기
    rm.set_is_user_stopped(channel_id, False)
    if bool(ch.get("record_enabled", True)):
        rm.set_status_reserved(channel_id, True)

    # 2) FSM에 실제 시작 요청
    try:
        await app.state.fsm.userStart(channel_id, is_user_request=is_user_request)

        try:
            await asyncio.sleep(0.15)
        except Exception:
            pass

        rec  = recorder_manager.get_status_recording(channel_id)
        rsv  = recorder_manager.get_status_reserved(channel_id)
        file = recorder_manager.get_recording_filename(channel_id) or ""

        state = "녹화 중" if rec and not rsv else ("예약녹화 중" if rsv else "대기 중")
        return {"status": "success", "state": state, "filename": file}
    except Exception as e:
        return {"status": "error", "message": str(e)}



# 특정 채널의 녹화를 중지하는 함수
async def stopRecordingForChannel(app: FastAPI, channel_id: str):
    try:
        last = recorder_manager.get_recording_filename(channel_id)

        # 1) 사용자 중지 플래그
        recorder_manager.set_is_user_stopped(channel_id, True)
        recorder_manager.set_status_reserved(channel_id, False)

        # 2) FSM 중지
        await app.state.fsm.userStop(channel_id)

        # 3) ★즉시 UI 혼선 방지: 스테일 상태 정리
        recorder_manager.set_status_recording(channel_id, False)
        recorder_manager.recording_remove_start_time(channel_id)
        recorder_manager.recording_remove_filename(channel_id)
        recorder_manager.clear_tasks_process(channel_id)

        # 4) 후처리 큐잉
        if last:
            asyncio.create_task(queueBatchPattern(channel_id, last))
        else:
            asyncio.create_task(queueBatchLast(channel_id))

        # 5) 마지막 파일명 반환(상위 API 응답용)
        return last

    except Exception as e:
        logger.warning(f"stopRecordingForChannel failed for {channel_id}: {e}")
        return None


# 모두 녹화하기 함수
async def startRecordingForAllChannels(app, is_user_request: bool=False):
    async with app.state.channels_lock:
        channels = [dict(c) for c in app.state.channels]

    results = {}
    tasks = []
    for ch in channels:
        cid = ch.get("id")
        if not cid or not bool(ch.get("record_enabled", True)):
            continue
        recorder_manager.set_is_user_stopped(cid, False)
        recorder_manager.set_status_reserved(cid, True)
        tasks.append(asyncio.create_task(app.state.fsm.userStart(cid)))
        # 일단 자리만 만들어 두고 나중에 실제 상태로 교정
        results[cid] = {"state": "예약녹화 중", "recording_duration": ""}

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    # 실제 상태로 정정: 녹화 > 예약 > 대기
    for cid in list(results.keys()):
        st  = recorder_manager.get_status_recording(cid)
        rsv = recorder_manager.get_status_reserved(cid)
        fsm = app.state.fsm.getState(cid)
        eff = bool(rsv or (fsm == "WATCHING"))
        results[cid]["state"] = "녹화 중" if st else ("예약녹화 중" if eff else "대기 중")

    return results


# 모든 플랫폼 동시에 모두 녹화 중지하기 함수
async def stopRecordingForAllChannels(app: FastAPI):
    # 1) 스냅샷
    pre_snap = {}
    async with app.state.channels_lock:
        channels = list(app.state.channels)
    for ch in channels:
        cid = ch.get("id")
        if cid:
            last = recorder_manager.get_recording_filename(cid)
            if last: pre_snap[cid] = last

    # 1.5) 선플래그: 루프가 즉시 STOP을 감지하도록 먼저 표시
    flagged = 0
    for ch in channels:
        cid = ch.get("id")
        if not cid:
            continue
        recorder_manager.set_is_user_stopped(cid, True)
        # UI가 잠깐 헷갈리지 않도록 예약 표시는 꺼둠 (루프 finalize에서 토글상태에 따라 다시 세움)
        recorder_manager.set_status_reserved(cid, False)
        flagged += 1
    logger.debug(f"set stop flag for {flagged} channels (pre-stopAll)")

    # 2) STOP
    await app.state.fsm.stopAll()
    logger.debug("FSM에게 일괄 STOPPED 전이를 요청했습니다.")

    # 3) 스냅샷 우선 큐잉 → 폴백
    for cid, last in pre_snap.items():
        asyncio.create_task(queueBatchPattern(cid, last))
    async with app.state.channels_lock:
        channels = list(app.state.channels)
    for ch in channels:
        cid = ch.get("id")
        if cid and cid not in pre_snap:
            asyncio.create_task(queueBatchLast(cid))


# IP 주소를 가져오는 함수
def getAddresses():
    with thread_lock:  # 전역 락 사용
        internal_ip = "127.0.0.1"
        local_ip = None
        external_ip = None

        if os.name == 'nt':
            # Windows: ipconfig 사용
            try:
                result = subprocess.run(['ipconfig'], capture_output=True, text=True, encoding='cp949')
                ip_address_match = re.search(r'IPv4 주소[^:]*:\s*([\d.]+)', result.stdout)
                if ip_address_match:
                    local_ip = ip_address_match.group(1)
                else:
                    local_ip = "내부 사설 IP 주소를 찾을 수 없습니다."
            except Exception as e:
                local_ip = f"내부 사설 IP 주소를 가져오는 중 오류 발생: {e}"
        else:
            # Linux: ip addr show 사용
            try:
                result = subprocess.run(['ip', 'addr', 'show'], capture_output=True, text=True)
                # 일반적으로 127.0.0.1은 제외하고 첫번째 inet 주소 사용
                ip_address_match = re.search(r'\s+inet\s+(\d+\.\d+\.\d+\.\d+)/', result.stdout)
                if ip_address_match:
                    local_ip = ip_address_match.group(1)
                else:
                    local_ip = "내부 사설 IP 주소를 찾을 수 없습니다."
            except Exception as e:
                local_ip = f"내부 사설 IP 주소를 가져오는 중 오류 발생: {e}"

        try:
            # 외부 공인 IP 주소 가져오기 (httpbin 사용)
            response = requests.get('https://httpbin.org/ip', timeout=5)
            if response.status_code == 200:
                external_ip = response.json()["origin"]
            else:
                external_ip = "공인 IP 주소를 가져오는 데 실패했습니다."
        except Exception as e:
            external_ip = f"공인 IP 주소를 가져오는 중 오류 발생: {e}"

        return internal_ip, local_ip, external_ip


# CPU 모델명 문자열을 반환 함수
def _getCpuName():
    global _CPU_NAME
    if _CPU_NAME:
        return _CPU_NAME

    name = None

    # 1) py-cpuinfo 우선
    try:
        if cpuinfo is not None:
            info = cpuinfo.get_cpu_info() or {}
            name = info.get('brand_raw') or info.get('brand')  # brand_raw 없을 수 있음
    except Exception:
        name = None

    # 2) Linux 전용 간단 폴백(/proc/cpuinfo)
    if not name:
        try:
            if os.path.exists("/proc/cpuinfo"):
                with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if "model name" in line:
                            name = line.split(":", 1)[1].strip()
                            break
        except Exception:
            pass

    # 3) 최후의 폴백
    if not name:
        name = platform.processor() or platform.machine() or "Unknown CPU"

    _CPU_NAME = name
    return _CPU_NAME

# 전역 표시용(1회 평가 후 캐시)
cpu_name = _getCpuName()


# 대시보드 디스크 라벨 정리
def _shortDiskLabel(p):
    mp = (p.mountpoint or "").strip().rstrip(os.sep)
    fs = (p.fstype or "").upper()

    if os.name == "nt":
        label = mp.upper() if (len(mp) >= 2 and mp[1] == ":") else (p.device or mp)
    else:
        if mp in ("/", "/home", "/boot"):
            label = mp
        elif mp.startswith("/sys/fs/cgroup/"):
            parts = [x for x in mp.split("/") if x]
            label = "cgroup/" + (parts[3] if len(parts) > 3 else "")
        elif len(mp) > 16:
            base = os.path.basename(mp)
            label = base if base else mp
        else:
            label = mp
    return label


# 보안 경로 정규화 헬퍼 함수
def _normalizeAllowedRoots(candidates: List[str]) -> List[str]:
    safe = []
    seen = set()
    for raw in candidates or []:
        if not raw:
            continue
        p = os.path.abspath(os.path.expanduser(raw.strip()))
        # 존재 + 디렉터리만 허용
        if not os.path.isdir(p):
            continue

        # 드라이브 루트/시스템 폴더 차단 (윈도우)
        lower = p.lower().replace('/', '\\')

        if os.name == 'nt':
            # 드라이브 루트(ex: C:\) 차단
            if re.match(r'^[a-z]:\\$', lower):
                continue
            # 대표 시스템 디렉터리 차단
            deny = ['\\windows\\', '\\program files\\', '\\program files (x86)\\', '\\programdata\\', '\\users\\public\\']
            if any(d in lower for d in deny):
                continue

        else:
            # 리눅스/유닉스: 루트(/) 자체, 핵심시스템 경로 차단
            deny = ['/', '/bin', '/sbin', '/etc', '/proc', '/sys', '/dev', '/run', '/var', '/usr']
            if p in deny or any(p.startswith(d + os.sep) for d in deny):
                continue

        if p not in seen:
            safe.append(p)
            seen.add(p)
    return safe


# Persistence helpers: 저장 디바운스/비동기 I/O
class DebouncedSaver:
    def __init__(self, app, delay=1.2):
        self.app = app
        self.delay = delay
        self._task = None
        self._pending = False

    def __call__(self, _unused=None):
        self._pending = True
        if not self._task or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def _run(self):
        while True:
            await asyncio.sleep(self.delay)
            self._pending = False
            try:
                async with self.app.state.channels_lock:
                    snap = list(self.app.state.channels)
                await asyncio.to_thread(saveChannels, snap)
            except Exception as e:
                logger.warning(f"DebouncedSaver failed: {e}")
            if not self._pending:
                break

    # 종료 직전 강제 저장
    async def flush(self):
        try:
            async with self.app.state.channels_lock:
                snap = list(self.app.state.channels)
            await asyncio.to_thread(saveChannels, snap)
        except Exception as e:
            logger.warning(f"DebouncedSaver.flush failed: {e}")



# WEB용 메타 시드 동시성 결정
def _seedMetaConcurrency() -> int:
    env = os.environ.get("SEED_META_CONCURRENCY", "").strip()
    if env.isdigit() and int(env) > 0:
        return max(1, min(12, int(env)))
    cfg = loadConfig() or {}
    val = cfg.get("seedMetaConcurrency", cfg.get("metaConcurrency", "auto"))
    if isinstance(val, int) and val > 0:
        return max(1, min(12, val))
    cores = os.cpu_count() or 2
    auto = int(cores * 0.75)
    return max(2, min(12, auto))


# 1회성 메타 시드 태스크
async def _seedMetadataWEB(app):
    chs = list(app.state.channels or [])
    if not chs:
        return
    conc = _seedMetaConcurrency()
    sem = asyncio.Semaphore(conc)
    logger.debug(f"(WEB) Seed meta concurrency = {conc}")

    async def _one(ch: dict):
        async with sem:
            try:
                payload = await app.state.meta_fetcher(ch)  # WEB은 _makeMetaFetcher(app)로 주입
                if isinstance(payload, dict):
                    async with app.state.channels_lock:
                        ch['live_title']    = payload.get('live_title',    ch.get('live_title', '정보 없음'))
                        ch['category']      = payload.get('category',      ch.get('category', '정보 없음'))
                        ch['thumbnail_url'] = payload.get('thumbnail_url', ch.get('thumbnail_url', '/static/img/default_thumbnail.png'))
                    await asyncio.sleep(0.03)  # 폭주 방지
            except Exception as e:
                logger.warning(f"(WEB) seed one failed: {e}")

    await asyncio.gather(*[asyncio.create_task(_one(ch)) for ch in chs])


# 녹화 현황 페이지
@app.get("/recording", response_class=HTMLResponse)
async def recording_page(request: Request, login: Any = Depends(requireLogin)):
    async with request.app.state.channels_lock:
        chs = [dict(c) for c in request.app.state.channels]

    updated = False
    for channel in chs:
        channel_id = channel['id']

        if "status" not in channel:
            channel['status'] = "대기 중"
            updated = True

        # 녹화 상태 확인
        recording_status = recorder_manager.get_status_recording(channel_id)
        reserved_status  = recorder_manager.get_status_reserved(channel_id)
        filename         = _getRecFilename(channel_id)

        # FSM.WATCHING 도 예약으로 취급
        fsm_state = request.app.state.fsm.getState(channel_id)
        effective_reserved = bool(reserved_status or (fsm_state == "WATCHING"))

        if recording_status:
            channel['status'] = "녹화 중"
            channel['filename'] = filename or '파일 없음'
        elif effective_reserved:
            channel['status'] = "예약녹화 중"
            channel['filename'] = "예약녹화 대기 중"
        else:
            channel['status'] = "대기 중"
            channel['filename'] = "녹화 중이 아닙니다."

        # 초기 표시용 필드
        channel['live_title'] = "불러오는 중..."
        channel['category'] = "불러오는 중..."
        channel['thumbnail_url'] = '/static/img/default_thumbnail.png'

    return templates.TemplateResponse('recording.html', {
        'request': request,
        'channels': chs,
        'program_version': PROGRAM_VERSION
    })


@app.get("/status")
async def get_status(request: Request):
    status = {}
    async with request.app.state.channels_lock:
        current_channels = list(request.app.state.channels)

    for channel in current_channels:
        cid = channel.get("id")
        rec  = recorder_manager.get_status_recording(cid)
        resv = recorder_manager.get_status_reserved(cid)

        # WATCHING은 예약으로 표시(단, 녹화 중일 땐 덮지 않음)
        fsm_state = request.app.state.fsm.getState(cid)
        if (fsm_state == "WATCHING") and (not rec):
            resv = True
        else:
            if rec:
                resv = False

        # 8초 유예 좀비 보정
        p = recorder_manager.get_tasks_process(cid)
        if rec:
            if (not p) or (p and p.returncode is not None):
                try:
                    ts = RecorderManager.recording_start_time.get(cid)
                    elapsed = (time.time() - float(ts)) if ts else 999
                except Exception:
                    elapsed = 999
                if elapsed >= 8:
                    recorder_manager.set_status_recording(cid, False)
                    recorder_manager.recording_remove_start_time(cid)
                    recorder_manager.recording_remove_filename(cid)
                    recorder_manager.clear_tasks_process(cid)
                    rec = False

        # 녹화 시간 계산
        duration_str = ""
        if rec:
            # 1) start ts(초) 기반
            ts = None
            try:
                ts = RecorderManager.recording_start_time.get(cid)
            except Exception:
                ts = None
            if ts:
                try:
                    elapsed = max(0, int(time.time() - float(ts)))
                    h = elapsed // 3600
                    m = (elapsed % 3600) // 60
                    s = elapsed % 60
                    duration_str = f"{h:02d}:{m:02d}:{s:02d}"
                except Exception:
                    duration_str = recorder_manager.get_recording_duration(cid) or "00:00:00"
            else:
                # 2) 폴백: 기존 매니저 제공값
                duration_str = recorder_manager.get_recording_duration(cid) or "00:00:00"

        # 현재 세션에 저장된 파일 경로를 가져와 파일명으로 변환
        fname = (
            recorder_manager.get_recording_filename(cid)
            or channel.get("output_path")
            or ""
        )

        status[cid] = {
            "recording": bool(rec),
            "reserved":  bool(resv),
            "duration":  duration_str,  
            "filename":  os.path.basename(fname) if fname else ""
        }
    return status


# ── 메인 대시보드용 채널 메타데이터 API ─────────────────────
@app.get("/api/channels")
async def api_channels(request: Request, login: Any = Depends(requireLogin)):
    async with request.app.state.channels_lock:
        chs = [dict(c) for c in request.app.state.channels]
    # 민감 필드 제외, 대시보드에 필요한 최소 필드만 반환
    safe = []
    for c in chs:
        safe.append({
            "id": c.get("id"),
            "channel_name": c.get("channel_name") or c.get("name") or "",
            "platform": c.get("platform") or "",
            "live_title": c.get("live_title") or "",
            "category": c.get("category") or "",
            "thumbnail_url": c.get("thumbnail_url") or "",
        })
    return safe


@app.get("/api/check_status/{channel_id}")
async def api_check_status(request: Request, channel_id: str, login: Any = Depends(requireLogin)):
    try:
        async with request.app.state.channels_lock:
            _channel = next((c for c in request.app.state.channels if c['id'] == channel_id), None)
            if not _channel:
                raise HTTPException(status_code=404, detail="Channel not found")
            channel = dict(_channel)

        channel_name = channel.get('name', 'Unknown Channel')
        platform = (channel.get('platform') or 'unknown').lower()

        recording_status         = recorder_manager.get_status_recording(channel_id)
        reserved_status          = recorder_manager.get_status_reserved(channel_id)
        filename                 = _getRecFilename(channel_id)
        recording_start_time_obj = _getRecStartTime(channel_id)
        recording_duration       = recorder_manager.get_recording_duration(channel_id)
        stop_requested           = recorder_manager.get_is_user_stopped(channel_id)

        # 녹화>예약>대기 우선순위 강제
        fsm_state = request.app.state.fsm.getState(channel_id)
        if recording_status:
            reserved_status = False
        elif fsm_state == "WATCHING":
            reserved_status = True

        effective_reserved = bool(reserved_status)
        channel_status = '녹화 중' if recording_status else ('예약녹화 중' if effective_reserved else '대기 중')

        # 8초 유예 좀비 보정 (동일)
        p = recorder_manager.get_tasks_process(channel_id)
        if recording_status:
            if (not p) or (p and p.returncode is not None):
                try:
                    ts = RecorderManager.recording_start_time.get(channel_id)
                    elapsed = (time.time() - float(ts)) if ts else 999
                except Exception:
                    elapsed = 999
                if elapsed >= 8:
                    recorder_manager.set_status_recording(channel_id, False)
                    recorder_manager.recording_remove_start_time(channel_id)
                    recorder_manager.recording_remove_filename(channel_id)
                    recorder_manager.clear_tasks_process(channel_id)
                    recording_status = False
                    filename = _getRecFilename(channel_id)
                    recording_start_time_obj = _getRecStartTime(channel_id)

        # 상태 문자열 교정
        if recording_status:
            channel_status = '녹화 중'
        elif effective_reserved:
            channel_status = '예약녹화 중'
        else:
            channel_status = '대기 중'

        # 예정/시작 시간 문자열
        scheduled_start_time = channel.get('scheduled_start_time')
        if isinstance(scheduled_start_time, datetime):
            scheduled_start_time_str = scheduled_start_time.strftime("%Y-%m-%d %H:%M:%S")
        elif isinstance(scheduled_start_time, str) and scheduled_start_time:
            scheduled_start_time_str = scheduled_start_time
        else:
            scheduled_start_time_str = "예정된 라이브 방송이 없습니다."

        if isinstance(recording_start_time_obj, datetime):
            recording_start_time_str = recording_start_time_obj.strftime("%Y-%m-%d %H:%M:%S")
        else:
            recording_start_time_str = '녹화 시작 시간이 설정되지 않았습니다.'

        # 녹화시간 계산
        if recording_status:
            try:
                if isinstance(recording_start_time_obj, datetime):
                    elapsed = max(0, int(time.time() - recording_start_time_obj.timestamp()))
                else:
                    ts = RecorderManager.recording_start_time.get(channel_id)
                    elapsed = max(0, int(time.time() - float(ts))) if ts else 0
                h = elapsed // 3600
                m = (elapsed % 3600) // 60
                s = elapsed % 60
                recording_duration = f"{h:02d}:{m:02d}:{s:02d}"
            except Exception:
                recording_duration = recording_duration or "00:00:00"
        else:
            recording_duration = "" 

        logger.debug(f"[{channel_name}] ({platform}) {filename} : {channel_status} "
              f"{recording_duration or '00:00:00'} Start: {recording_start_time_str}")

        return JSONResponse(content={
            'status': 'success',
            'state': channel_status,
            'filename': filename or '녹화 파일이 없습니다.',
            'recording_duration': recording_duration or '00:00:00',
            'recording_start_time': recording_start_time_str,
            'scheduled_start_time': scheduled_start_time_str,
            'stop_requested': recorder_manager.get_is_user_stopped(channel_id)
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"check_status 오류 발생: {e}")
        import traceback; print(traceback.format_exc())
        return JSONResponse(content={'status': 'error', 'message': str(e)}, status_code=500)


# 치지직 및 유튜브 메타데이터 통합 API
@app.get("/api/update_metadata/{channel_id}")
async def update_metadata(channel_id: str, request: Request, login: Any = Depends(requireLogin)):
    # 1) channel 스냅샷
    async with request.app.state.channels_lock:
        channel = next((c for c in request.app.state.channels if c['id'] == channel_id), None)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    platform = (channel.get('platform') or 'unknown').lower()

    # 2) 캐시-우선 응답 (stale면 백그라운드에서 자동 갱신)
    payload, from_cache, fresh = await getMetadataCached(
        request.app,
        channel_id,
        platform,
        request.app.state.meta_fetcher,
        request.app.state.save_debounced,
        request.app.state.channels_lock,
    )

    # 3) 필요 시 ISO 문자열 보정
    if payload and isinstance(payload, dict):
        dt = payload.get('scheduled_start_time_dt')
        if isinstance(dt, datetime):
            payload['scheduled_start_time_str'] = dt.isoformat()
            payload.pop('scheduled_start_time_dt', None)

    return JSONResponse(content={
        'status': 'success',
        'from_cache': from_cache,
        'fresh': fresh,
        'metadata': payload or {}
    })


# 썸네일 상태갱신 API
@app.get("/api/thumbnail_status")
async def api_thumbnail_status(request: Request, login: Any = Depends(requireLogin)):
    # 캐시-우선 썸네일 목록 (stale이면 백그라운드 갱신 트리거)
    async with request.app.state.channels_lock:
        chs = list(request.app.state.channels)
    items = await getThumbnailsCached(
        request.app, chs, request.app.state.meta_fetcher, request.app.state.save_debounced, request.app.state.channels_lock
    )

    try:
        for it in items:
            cid = str(it.get("id") or "")
            p   = (it.get("platform") or "").lower()

    except Exception:
        pass

    return JSONResponse(content={'channels': items})


# 개별 녹화시작 API 함수
@app.post("/api/start_recording/{channel_id}")
async def api_start_recording(channel_id: str, request: Request, login: Any = Depends(requireLogin)):
    try:
        body = await request.json()
        is_user_request = bool(body.get('is_user_request', False))
    except Exception:
        is_user_request = False

    await startRecordingForChannel(request.app, channel_id, is_user_request=is_user_request)

    # 간격으로 최대 2초 대기: 프로세스 핸들 or recording=True 감지
    for _ in range(20):
        rec  = recorder_manager.get_status_recording(channel_id)
        proc = recorder_manager.get_tasks_process(channel_id)
        if rec or (proc and proc.returncode is None):
            # 실제로 기동됨 → 예약 플래그는 의미없도록 덮어씀
            effective_reserved = False
            break
        await asyncio.sleep(0.1)

    else:
        # 타임아웃 시 마지막 스냅샷으로 계산
        rec  = recorder_manager.get_status_recording(channel_id)
        resv = recorder_manager.get_status_reserved(channel_id)
        fsm_state = request.app.state.fsm.getState(channel_id)
        effective_reserved = bool(resv or (fsm_state == "WATCHING"))

    state = '녹화 중' if rec else ('예약녹화 중' if effective_reserved else '대기 중')
    return JSONResponse({
        'status': 'success',
        'message': '시작 요청을 접수했습니다.',
        'state': state
    })


# 개별 녹화중지 API 함수
@app.post("/api/stop_recording/{channel_id}")
async def api_stop_recording(channel_id: str, request: Request, login: Any = Depends(requireLogin)):
    # 중지 실행 + 마지막 파일명 획득
    last = await stopRecordingForChannel(request.app, channel_id)

    # 표시 우선순위: 녹화 > 예약 > 대기
    state    = recorder_manager.get_status_recording(channel_id)
    reserved = recorder_manager.get_status_reserved(channel_id)

    # FSM WATCHING도 예약으로 취급
    fsm_state = request.app.state.fsm.getState(channel_id)
    effective_reserved = bool(reserved or (fsm_state == "WATCHING"))

    # 녹화가 True면 무조건 '녹화 중'이 우선
    resolved = '녹화 중' if state else ('예약녹화 중' if effective_reserved else '대기 중')

    return JSONResponse({
        'status': 'success',
        'state': resolved,
        'filename': last or '녹화 파일이 없습니다.'
    })



# 모두 녹화시작 API 함수
@app.post("/api/start_all_recording")
async def api_start_all_recording(request: Request, login: Any = Depends(requireLogin)):
    try:
        body = await request.json()
        is_user_request = bool(body.get("is_user_request", False))
    except Exception:
        is_user_request = False

    results = await startRecordingForAllChannels(request.app, is_user_request=is_user_request)
    return JSONResponse({'status': 'success', 'message': '일괄 시작 요청 접수', 'channels_status': results})


# 모두 녹화중지 API 함수
@app.post("/api/stop_all_recording")
async def api_stop_all_recording(request: Request, login: Any = Depends(requireLogin)):
    await stopRecordingForAllChannels(request.app)
    return JSONResponse({'status': 'success', 'message': '일괄 중지 요청 접수'})


# 채널별 녹화 활성/비활성 토글 API 
@app.post("/api/toggle_record_enabled/{channel_id}")
async def toggle_record_enabled(channel_id: str, request: Request, login: Any = Depends(requireLogin)):
    async with request.app.state.channels_lock:
        chs = request.app.state.channels
        channel = next((c for c in chs if c['id'] == channel_id), None)
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")

        before = toBool(channel.get('record_enabled', True))
        # 토글
        channel['record_enabled'] = (not before)
        # 저장 직전 스냅샷
        snapshot = list(chs)

    request.app.state.save_debounced(None)

    if channel['record_enabled'] is False:
        # OFF시 현재 감시/워커만 정리 (녹화 중이면 이번 회차는 유지, 다음 회차부터 반영)
        await request.app.state.fsm.onRecordEnabledChanged(channel_id, enabled=False)
    else:

        try:
            channel['status'] = "대기 중"
        except Exception:
            pass

    logger.debug(f"toggle_record_enabled: {channel['name']}({channel_id}) {before} -> {channel['record_enabled']}")
    return {"status": "success", "channel_id": channel_id, "record_enabled": channel['record_enabled']}


# 웹 대시보드에 매트릭 API
@app.get("/api/sys_metrics")
async def api_sys_metrics():
    try:
        # CPU: 첫 호출 0% 이슈 회피 (interval>0)  :contentReference[oaicite:4]{index=4}
        cpu_pct = float(psutil.cpu_percent(interval=0.2))

        # MEM: 즉시값
        vm = psutil.virtual_memory()

        # NET: 요청 내 2번 샘플링(워커 분산 상관없이 즉시값 보장)  :contentReference[oaicite:5]{index=5}
        n1 = psutil.net_io_counters(pernic=False)
        t1 = time.time()
        await asyncio.sleep(0.2)
        n2 = psutil.net_io_counters(pernic=False)
        t2 = time.time()
        dt = t2 - t1
        if dt <= 0:
            dt = 0.001
        up_bps = max(0.0, float(n2.bytes_sent - n1.bytes_sent) / dt)
        down_bps = max(0.0, float(n2.bytes_recv - n1.bytes_recv) / dt)

        # DISK: 포괄 수집 + 접근불가 스킵 + 윈도우 드라이브 폴백  :contentReference[oaicite:6]{index=6}
        disks = []
        try:
            parts = psutil.disk_partitions(all=True)
        except Exception:
            parts = []

        seen = set()
        for p in parts:
            mp = (p.mountpoint or "").strip()
            if not mp or mp in seen:
                continue

            # 임시/가상 파일시스템 필터
            EPHEMERAL = {"tmpfs","proc","sysfs","cgroup","cgroup2","squashfs","devpts","overlay"}
            if (p.fstype or "").lower() in EPHEMERAL and mp not in ("/", "/home", "/boot"):
                continue

            try:
                u = psutil.disk_usage(mp)
            except Exception:
                continue
            seen.add(mp)
            disks.append({
                "device": p.device or mp,
                "mountpoint": mp,
                "label": _shortDiskLabel(p),     
                "fstype": (p.fstype or "").lower(),
                "total": int(u.total),
                "used": int(u.used),
                "free": int(u.free),
                "percent": float(u.percent)
            })


        if not disks and os.name == 'nt':
            for letter in string.ascii_uppercase:
                root = f"{letter}:\\"
                if not os.path.exists(root):
                    continue
                try:
                    u = shutil.disk_usage(root)
                except Exception:
                    continue
                disks.append({
                    "device": root,
                    "mountpoint": root,
                    "fstype": "",
                    "total": int(u.total),
                    "used": int(u.used),
                    "free": int(u.free),
                    "percent": float((u.used / u.total * 100.0) if u.total else 0.0)
                })

        if len(disks) > 10:
            disks = disks[:10]

        return JSONResponse(content={
            "cpu": {"name": cpu_name,
                    "percent": cpu_pct,
                    "cores": psutil.cpu_count(logical=True)},
            "memory": {"total": int(vm.total),
                       "used": int(vm.used),
                       "free": int(vm.available),
                       "percent": float(vm.percent)},
            "network": {
                "up_bps": float(up_bps),
                "down_bps": float(down_bps),
                "bytes_sent": int(n2.bytes_sent),
                "bytes_recv": int(n2.bytes_recv)
            },
            "disks": disks
        })
    except Exception as e:
        tb = traceback.format_exc()
        logger.info(f"[ERROR] {e}\n{tb}")  # 콘솔에 전체 트레이스백 노출
        return JSONResponse(
            content={"status": "error", "message": str(e), "traceback": tb},
            status_code=500
        )


# 메인 페이지 라우트
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    config = request.app.state.config
    loginMode = config.get('loginMode', False)  # 로그인 모드 상태 확인

    # 로그인되지 않은 상태에서 로그인 모드가 활성화된 경우
    if loginMode and not request.session.get('logged_in'):
        return templates.TemplateResponse('index.html', {
            'request': request,
            'config': config,
            'loginMode': loginMode,
            'program_name': PROGRAM_NAME,
            'program_version': PROGRAM_VERSION
        })
    else:
        # 로그인된 상태 또는 로그인 모드가 비활성화된 경우
        return templates.TemplateResponse('index.html', {
            'request': request,
            'config': config,
            'loginMode': loginMode,
            'program_name': PROGRAM_NAME,
            'program_version': PROGRAM_VERSION
        })


# 로그인 라우트
@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    try:
        # 계정 정보를 로드합니다.
        account = loadAccount()
        
        # 계정 정보가 존재하고 비밀번호가 일치할 경우
        if account and account['username'] == username and check_password_hash(account['password'], password):
            # 세션에 로그인 상태 저장
            request.session['logged_in'] = True
            return JSONResponse(
                content={"status": "success", "message": "로그인 성공", "redirect_url": "/"},
                status_code=200
            )
        
        else:
            # 로그인 실패 시 JSON 응답을 반환 (리다이렉션 없음)
            return JSONResponse(
                content={"status": "error", "message": "아이디 또는 비밀번호가 올바르지 않습니다."},
                status_code=401,  # 401 Unauthorized 상태 코드
                headers={"Content-Type": "application/json"}
            )
    
    except Exception as e:
        # 예외 처리
        logger.info(f"로그인 중 오류 발생: {e}")
        return JSONResponse(
            content={"status": "error", "message": "로그인 처리 중 오류가 발생했습니다."},
            status_code=500
        )


# 로그아웃 라우트
@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url='/', status_code=302)


# GET 요청을 처리하여 계정 생성 페이지를 렌더링
@app.get("/register")
async def register_page(request: Request):
    account = loadAccount()
    loginMode = request.app.state.config.get('loginMode', False)
    need_account = request.query_params.get('need_account') 

    if account:
        error_message = "이미 계정이 존재합니다. 추가 계정을 만들 수 없습니다."

        return templates.TemplateResponse(
            'register.html',
            {'request': request, 'error_message': error_message, 'loginMode': loginMode, 'program_version': PROGRAM_VERSION},
            status_code=400
        )

    return templates.TemplateResponse(
        'register.html',
        {
            'request': request,
            'loginMode': loginMode,
            'info_message': "로그인 모드를 켰습니다. 먼저 관리자 계정을 생성하세요." if need_account else None,
            'program_version': PROGRAM_VERSION
        }
    )


# 계정 생성 폼을 처리하는 POST 요청
@app.post("/register")
async def register(request: Request, username: str = Form(...), password: str = Form(...), password_confirm: str = Form(...)):
    account = loadAccount()
    
    # 계정이 이미 존재하면 계정 생성 금지
    if account:
        error_message = "이미 계정이 존재합니다. 추가 계정을 만들 수 없습니다."
        return templates.TemplateResponse('register.html', {
            'request': request,
            'error_message': error_message,
            'program_version': PROGRAM_VERSION
        }, status_code=400)

    # 비밀번호 확인
    if password != password_confirm:

        return templates.TemplateResponse('register.html', {
            'request': request,
            'error_message': "비밀번호가 일치하지 않습니다.",
            'program_version': PROGRAM_VERSION
        })

    # 비밀번호 해시화 후 계정 저장
    hashed_password = generate_password_hash(password)
    account = {"username": username, "password": hashed_password}
    saveAccount(account)

    # 계정 생성 후 메인 페이지로 리다이렉트
    return RedirectResponse(url='/', status_code=302)


# 계정 수정/삭제 관련 라우트
@app.post("/updateAccount")
async def updateAccount(
    request: Request, 
    username: str = Form(...), 
    current_password: str = Form(...), 
    new_password: str = Form(None), 
    new_password_confirm: str = Form(None), 
    action: str = Form(...)
):
    try:
        account = loadAccount()  # 계정 정보 로드

        # 로그를 추가하여 디버깅
        logger.info(f"Received request for action: {action}")
        logger.info(f"Username: {username}, Current Password: {current_password}, Action: {action}")

        if action == "update":  # 계정 수정
            if account:
                is_password_valid = check_password_hash(account['password'], current_password)
                if not is_password_valid:
                    return JSONResponse(
                        content={"status": "error", "message": "기존 비밀번호가 일치하지 않습니다."},
                        status_code=400
                    )
                if new_password != new_password_confirm:
                    return JSONResponse(
                        content={"status": "error", "message": "새 비밀번호가 일치하지 않습니다."},
                        status_code=400
                    )

                # 비밀번호 해시 업데이트
                hashed_password = generate_password_hash(new_password)
                account['username'] = username
                account['password'] = hashed_password
                saveAccount(account)

                # 세션 정리 및 로그아웃 처리
                request.session.clear()  # 기존 세션 제거
                return JSONResponse(
                    content={"status": "success", "message": "계정이 성공적으로 수정되었습니다. 로그아웃 후 메인 페이지로 이동합니다.", "redirect_url": "/logout"},
                    status_code=200
                )

        elif action == "delete":  # 계정 삭제
            logger.info(f"Attempting to delete account: {username}")

            # 삭제는 username과 current_password만 필요
            if account and check_password_hash(account['password'], current_password):
                if os.path.exists(LOGIN_PATH):
                    os.remove(LOGIN_PATH)
                    request.session.clear()  # 세션 정리
                    return JSONResponse(
                        content={"status": "success", "message": "계정이 삭제되었습니다.", "redirect_url": "/logout"},
                        status_code=200
                    )
                else:
                    return JSONResponse(
                        content={"status": "error", "message": "삭제할 계정이 없습니다."},
                        status_code=400
                    )
            else:
                return JSONResponse(
                    content={"status": "error", "message": "기존 비밀번호가 일치하지 않습니다."},
                    status_code=400
                )
    except Exception as e:
        logger.info(f"Exception: {str(e)}")  # 예외 발생 시 디버그 메시지 출력
        return JSONResponse(
            content={"status": "error", "message": f"계정 처리 중 오류 발생: {str(e)}"},
            status_code=500
        )


@app.post("/api/save_chzzk_cookies")
async def save_chzzk_cookies(request: Request, body: dict = Body(...), login: Any = Depends(requireLogin)):
    saveCookies(body)
    request.app.state.chzzk_cookies = body
    return {"status": "ok"}


@app.post("/api/save_youtube_cookie_file")
async def save_youtube_cookie_file(request: Request, login: Any = Depends(requireLogin)):
    path = yloadCookies()  # 업로드/경로 조정 로직 후 반환
    request.app.state.youtube_cookie_path = path
    return {"status": "ok", "path": path}


@app.post("/api/save_config")
async def save_config_api(request: Request, body: dict = Body(...), login: Any = Depends(requireLogin)):
    merged = saveConfig(body)                  
    request.app.state.config = merged            
    return {"status": "ok", "config": merged}   


# 계정 사용자 정보 전달 
@app.get("/user_info")
async def user_info(request: Request):
    account = loadAccount()
    config = request.app.state.config or {}
    loginMode  = bool(config.get('loginMode', False))
    enableTray = bool(config.get('enableTray', False))

    payload = {
        "config": {
            "loginMode":  loginMode,
            "enableTray": enableTray,   
        }
    }

    if account and request.session.get('logged_in'):
        username = account.get('username', 'Unknown User')
        payload.update({"logged_in": True, "username": username})
    else:
        payload.update({"logged_in": False, "username": None})

    return JSONResponse(content=payload)


@app.get("/channels", response_class=HTMLResponse)
async def channelsPage(request: Request, login: Any = Depends(requireLogin)):
    async with request.app.state.channels_lock:
        chs = list(request.app.state.channels)

    return templates.TemplateResponse('channels.html', {
        'request': request,
        'channels': chs,
        'program_version': PROGRAM_VERSION
    })


# 채널 추가 API 함수
@app.post("/api/channels")
async def addChannel(request: Request, login: Any = Depends(requireLogin)):
    try:
        body = await request.body()
        if not body:
            raise HTTPException(status_code=400, detail="요청 본문이 비어 있습니다.")
        new_channel = await request.json()

        # 플랫폼/필드 보정
        if new_channel["platform"] == "youtube":
            new_channel["extension"] = ".mp4"

        # recordWatchParty 정규화
        rw = toBool(new_channel.get("recordWatchParty", False))
        if new_channel.get("platform") == "youtube":
            rw = False
        new_channel["recordWatchParty"] = rw

        # watchPartyExcludeTags 정규화(문자열/배열 모두 허용)
        def _norm_exclude(v):
            if isinstance(v, str):
                items = [s.strip() for s in v.split(",")]
            elif isinstance(v, list):
                items = [str(s).strip() for s in v]
            else:
                items = []
            seen = set(); res = []
            for s in items:
                k = s.lower()
                if s and k not in seen:
                    seen.add(k); res.append(s)
            return res

        new_channel["watchPartyExcludeTags"] = _norm_exclude(new_channel.get("watchPartyExcludeTags"))

        # channelId → id 치환
        if "channelId" in new_channel:
            new_channel["id"] = new_channel.pop("channelId")

        # 유효성 검사
        if new_channel["platform"] not in ["chzzk", "youtube"]:
            raise HTTPException(status_code=400, detail="잘못된 플랫폼 값입니다.")
        required = ("platform", "id", "name", "output_dir", "quality", "extension")
        if not all(k in new_channel for k in required):
            raise HTTPException(status_code=400, detail="필수 필드가 누락되었습니다.")

        # 기본값
        new_channel.setdefault("record_enabled", True)

        # 락 안: 메모리만 수정
        async with request.app.state.channels_lock:
            chs = request.app.state.channels
            chs.append(new_channel)
            snapshot = list(chs)  # 저장용 스냅샷

        request.app.state.save_debounced(None)

        try:
            RecorderManager.setChannels(snapshot)
        except Exception as _e:
            logger.warning(f"setChannels 실패(무시): {_e}")

        logger.debug("새 채널이 추가되었습니다.")
        return JSONResponse(content={'status': 'success'})

    except HTTPException as http_exc:
        logger.error(f"채널 추가 중 오류 발생: {http_exc.detail}")
        raise
    except Exception as e:
        logger.error(f"채널 추가 중 오류 발생: {e}")
        raise HTTPException(status_code=500, detail="채널 추가 중 오류 발생")


# 채널 수정 API 함수
@app.put("/api/channels/{channel_id}")
async def editChannel(channel_id: str, request: Request, login: Any = Depends(requireLogin)):
    try:
        updated_channel = await request.json()

        # 락 안: 대상 찾고 메모리만 수정
        async with request.app.state.channels_lock:
            chs = request.app.state.channels
            target = next((c for c in chs if c.get('id') == channel_id), None)
            if not target:
                raise HTTPException(status_code=404, detail="Channel not found")

            # 유효 플랫폼 결정 (payload 우선)
            effective_platform = updated_channel.get("platform", target.get("platform"))

            # 유튜브면 확장자 강제 .mp4
            if effective_platform == "youtube":
                updated_channel["extension"] = ".mp4"

            # recordWatchParty 정규화
            if "recordWatchParty" in updated_channel:
                rw = toBool(updated_channel["recordWatchParty"])
                if effective_platform == "youtube":
                    rw = False
                updated_channel["recordWatchParty"] = rw

            # watchPartyExcludeTags 정규화
            def _norm_exclude(v):
                if isinstance(v, str):
                    items = [s.strip() for s in v.split(",")]
                elif isinstance(v, list):
                    items = [str(s).strip() for s in v]
                else:
                    items = []
                seen = set(); res = []
                for s in items:
                    k = s.lower()
                    if s and k not in seen:
                        seen.add(k); res.append(s)
                return res

            if "watchPartyExcludeTags" in updated_channel:
                updated_channel["watchPartyExcludeTags"] = _norm_exclude(updated_channel["watchPartyExcludeTags"])

            updated_channel['id'] = channel_id 
            target.update(updated_channel)

            snapshot = list(chs)

        request.app.state.save_debounced(None)

        try:
            RecorderManager.setChannels(snapshot)
        except Exception as _e:
            logger.warning(f"setChannels 실패(무시): {_e}")

        return JSONResponse(content={'status': 'success'})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"채널 수정 중 오류 발생: {e}")
        raise HTTPException(status_code=500, detail="채널 수정 중 오류 발생")



# 채널 삭제 API 함수
@app.delete("/api/channels/{channel_id}")
async def deleteChannel(channel_id: str, request: Request, login: Any = Depends(requireLogin)):
    try:
        # 락 안: 메모리만 수정
        async with request.app.state.channels_lock:
            chs = request.app.state.channels
            new_list = [c for c in chs if c.get('id') != channel_id]
            if len(new_list) == len(chs):
                raise HTTPException(status_code=404, detail="Channel not found")

            chs[:] = new_list  # 제자리 갱신
            snapshot = list(chs)  # 저장용 스냅샷

        request.app.state.save_debounced(None)

        try:
            RecorderManager.setChannels(snapshot)
        except Exception as _e:
            logger.warning(f"setChannels 실패(무시): {_e}")

        return JSONResponse(content={'status': 'success'})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"채널 삭제 중 오류 발생: {e}")
        raise HTTPException(status_code=500, detail="채널 삭제 중 오류 발생")


@app.get("/cookies", response_class=HTMLResponse)
async def getCookies(request: Request, login: Any = Depends(requireLogin)):
    cookies = loadCookies()  # 디스크에서 항상 최신본

    return templates.TemplateResponse('cookies.html', {
        'request': request,
        'cookies': cookies,
        'program_version': PROGRAM_VERSION
    })


@app.post("/cookies")
async def updateCookies(request: Request, login: Any = Depends(requireLogin)):
    try:
        new_cookies = await request.json()
        if not new_cookies:
            return JSONResponse(content={'status': 'error', 'message': '쿠키 데이터가 비어 있습니다.'}, status_code=400)

        saveCookies(new_cookies)
        request.app.state.chzzk_cookies = new_cookies 

        logger.info(f"쿠키가 성공적으로 저장되었습니다: {new_cookies}")
        return JSONResponse(content={'status': 'success'})

    except Exception as e:
        logger.info(f"쿠키 업데이트 중 오류 발생: {e}")
        return JSONResponse(content={'status': 'error', 'message': '쿠키 업데이트 중 오류 발생'}, status_code=500)


# 파일관리 페이지
@app.get("/files", response_class=HTMLResponse)
async def filesPage(request: Request, login: Any = Depends(requireLogin)):
    cfg = request.app.state.config
    # roots 존재 여부와 무관하게, 스위치만으로 활성화
    enabled = bool(cfg.get("fileManagerEnabled"))
    roots = cfg.get("fileManagerRoots") or []

    return templates.TemplateResponse(
        "files.html",
        {
            "request": request,
            "loginMode": cfg.get("loginMode", False),
            "fm_enabled": enabled,
            "fm_roots": roots,
            "program_version": PROGRAM_VERSION,
        },
    )


# 사용량/목록 API
@app.get("/api/files/usage")
async def api_files_usage(request: Request, login: Any = Depends(requireLogin)):
    cfg = request.app.state.config
    async with request.app.state.channels_lock:
        roots = buildAllowedRoots(cfg, request.app.state.channels)
    return {"status": "ok", "volumes": listDisks(roots)}


# 파일 목록
@app.get("/api/files/list")
async def api_files_list(
    request: Request,
    path: str,
    show_hidden: bool = Query(False),
    login: Any = Depends(requireLogin)
):
    cfg = request.app.state.config
    async with request.app.state.channels_lock:
        roots = buildAllowedRoots(cfg, request.app.state.channels)
        busy  = busyFilePaths(recorder_manager, request.app.state.channels)

    rp = ensureInRoots(path, roots)
    items = listDir(rp, show_hidden=show_hidden)
    for it in items:
        it["locked"] = isLocked(it["path"], busy)
    return {"status": "ok", "path": rp, "items": items}


# 루트 목록
@app.get("/api/files/roots")
async def api_files_roots(request: Request, login: Any = Depends(requireLogin)):
    cfg = request.app.state.config
    if not cfg.get("fileManagerEnabled", False):
        raise HTTPException(status_code=403, detail="File manager disabled")

    async with request.app.state.channels_lock:
        roots = buildAllowedRoots(cfg, request.app.state.channels)

    # 블랙리스트(오픈) 모드(["*"])일 땐 시스템 마운트 루트들을 반환
    if roots == ["*"]:
        roots_list = listMountRoots()
        default_path = os.path.expanduser("~") if os.path.isdir(os.path.expanduser("~")) else (roots_list[0] if roots_list else None)
    else:
        roots_list = roots
        default_path = roots_list[0] if roots_list else None

    return {"roots": roots_list, "default": default_path}


# 파일 목록 호출(프론트가 /api/files/ls 호출)
@app.get("/api/files/ls")
async def api_files_ls(
    request: Request,
    path: str,
    show_hidden: bool = Query(False),
    login: Any = Depends(requireLogin)
):
    cfg = request.app.state.config
    async with request.app.state.channels_lock:
        roots = buildAllowedRoots(cfg, request.app.state.channels)
        busy  = busyFilePaths(recorder_manager, request.app.state.channels)

    # 1) 허용 루트 검사 → 403
    try:
        rp = ensureInRoots(path, roots)
    except PermissionError:
        # 프론트의 보안 안내문 포맷터가 이 문구/상태코드를 잡아줍니다.
        raise HTTPException(status_code=403, detail="outside allowed roots")
    except Exception:
        # 형식이 이상한 path 등은 400
        raise HTTPException(status_code=400, detail="invalid path")

    # 2) 존재/타입 검사 → 404
    if not os.path.isdir(rp):
        raise HTTPException(status_code=404, detail="path not found")

    # 3) 목록 조회(권한 문제 등) → 403
    try:
        items = listDir(rp, show_hidden=show_hidden)
    except PermissionError:
        raise HTTPException(status_code=403, detail="permission denied")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="path not found")
    except OSError:
        # 접근 금지/장치 오류 등 기타 OS 에러는 보수적으로 403
        raise HTTPException(status_code=403, detail="access denied")

    for it in items:
        it["locked"] = isLocked(it["path"], busy)

    return {"status": "ok", "path": rp, "items": items}


# 디스크 사용량
@app.get("/api/files/disk-usage")
async def api_files_disk_usage(request: Request, paths: List[str] = Query(default=None), login: Any = Depends(requireLogin)):
    cfg = request.app.state.config
    if paths:
        roots = [p for p in paths if os.path.isdir(p)]
    else:
        # paths 미지정: 마운트 루트 전체 또는 설정 루트 사용
        async with request.app.state.channels_lock:
            built = buildAllowedRoots(cfg, request.app.state.channels)
        roots = listMountRoots() if built == ["*"] else built

    usages = []
    for r in roots:
        try:
            d = diskUsageFor(r)
            # 프론트 표시용 label
            d["label"] = r
            usages.append(d)
        except Exception:
            continue
    return {"status":"ok", "usages": usages}


# 4) 파일 다운로드 
@app.get("/api/files/download")
async def api_files_download(request: Request, path: str, login: Any = Depends(requireLogin)):
    async with request.app.state.channels_lock:
        roots = buildAllowedRoots(request.app.state.config, request.app.state.channels)

    rp = ensureInRoots(path, roots)
    if not os.path.isfile(rp):
        raise HTTPException(status_code=404, detail="File not found")

    filename = os.path.basename(rp)
    return FileResponse(rp, filename=filename, media_type="application/octet-stream")



# 경로 만들기 API
@app.post("/api/files/mkdir")
async def api_files_mkdir(request: Request, body: dict = Body(...), login: Any = Depends(requireLogin)):
    if request.app.state.config.get("fileManagerReadOnly", False):
        raise HTTPException(status_code=403, detail="Read-only mode")
    parent  = body.get("path")
    newName = body.get("new_name")
    if not parent or not newName:
        raise HTTPException(status_code=400, detail="path/new_name required")

    async with request.app.state.channels_lock:
        roots = buildAllowedRoots(request.app.state.config, request.app.state.channels)
    parent = ensureInRoots(parent, roots)
    created = mkdirPath(parent, newName)
    return {"status":"ok", "created": created}


# 경로 수정 API
@app.post("/api/files/rename")
async def api_files_rename(request: Request, body: dict = Body(...), login: Any = Depends(requireLogin)):
    if request.app.state.config.get("fileManagerReadOnly", False):
        raise HTTPException(status_code=403, detail="Read-only mode")
    src = body.get("path"); newName = body.get("new_name")
    if not src or not newName:
        raise HTTPException(status_code=400, detail="path/new_name required")
    async with request.app.state.channels_lock:
        roots = buildAllowedRoots(request.app.state.config, request.app.state.channels)
        busy  = busyFilePaths(recorder_manager, request.app.state.channels)
    src = ensureInRoots(src, roots)
    if isLocked(src, busy): raise HTTPException(status_code=423, detail="Locked (recording)")
    dst = renamePath(src, newName)
    return {"status":"ok", "path": dst}


# 파일 이동 API
@app.post("/api/files/move")
async def api_files_move(request: Request, body: dict = Body(...), login: Any = Depends(requireLogin)):
    if request.app.state.config.get("fileManagerReadOnly", False):
        raise HTTPException(status_code=403, detail="Read-only mode")

    srcs = body.get("srcs") or ([] if not body.get("src") else [body.get("src")])
    dstDir = body.get("dst_dir")
    if not srcs or not dstDir:
        raise HTTPException(status_code=400, detail="src/srcs and dst_dir required")

    async with request.app.state.channels_lock:
        roots = buildAllowedRoots(request.app.state.config, request.app.state.channels)
        busy  = busyFilePaths(recorder_manager, request.app.state.channels)

    dstDir = ensureInRoots(dstDir, roots)
    moved = []
    for s in srcs:
        rp = ensureInRoots(s, roots)
        if isLocked(rp, busy):
            raise HTTPException(status_code=423, detail=f"Locked: {rp}")
        moved.append(movePath(rp, dstDir))
    return {"status":"ok", "moved": moved}


# 파일 삭제 API
@app.post("/api/files/delete")
async def api_files_delete(request: Request, body: dict = Body(...), login: Any = Depends(requireLogin)):
    if request.app.state.config.get("fileManagerReadOnly", False):
        raise HTTPException(status_code=403, detail="Read-only mode")

    paths = body.get("paths") or ([] if not body.get("path") else [body.get("path")])
    hard  = bool(body.get("hard", False))
    if not paths:
        raise HTTPException(status_code=400, detail="paths or path required")

    async with request.app.state.channels_lock:
        roots = buildAllowedRoots(request.app.state.config, request.app.state.channels)
        busy  = busyFilePaths(recorder_manager, request.app.state.channels)

    def pickRootFor(p: str) -> str:
        rp = normPath(p)
        # 와일드카드 모드(["*"])에서는 같은 폴더 아래 .trash 사용
        if roots == ["*"]:
            return os.path.dirname(rp)
        candidates = [r for r in roots if rp.startswith(normPath(r))]
        if not candidates:
            raise PermissionError("Outside roots")
        return max(candidates, key=lambda r: len(normPath(r)))

    deleted = []
    for p in paths:
        rp = ensureInRoots(p, roots)
        if isLocked(rp, busy):
            raise HTTPException(status_code=423, detail=f"Locked: {rp}")
        if hard or not request.app.state.config.get("trashEnabled", True):
            hardDelete(rp)
            deleted.append(rp)
        else:
            rootForTrash = pickRootFor(rp)
            deleted.append(softDelete(rp, rootForTrash))
    return {"status":"ok", "deleted": deleted}


# 파일매니저 스트림복사 API함수
@app.post("/api/files/streamcopy")
async def api_files_streamcopy(
    request: Request,
    body: dict = Body(...),
    login: Any = Depends(requireLogin),
):
    # 읽기전용 모드 차단
    if request.app.state.config.get("fileManagerReadOnly", False):
        raise HTTPException(status_code=403, detail="Read-only mode")

    srcs = body.get("paths") or []
    if not srcs:
        raise HTTPException(status_code=400, detail="paths required")

    async with request.app.state.channels_lock:
        roots = buildAllowedRoots(request.app.state.config, request.app.state.channels)
        busy  = busyFilePaths(recorder_manager, request.app.state.channels)

    results = []

    for s in srcs:
        try:
            rp = ensureInRoots(s, roots)
            if not os.path.isfile(rp):
                raise HTTPException(status_code=400, detail=f"Not a file: {rp}")
            if isLocked(rp, busy):
                raise HTTPException(status_code=423, detail=f"Locked (recording): {rp}")

            # 공용 함수 사용 
            from module.file_manager import streamCopyFile
            dst = await asyncio.to_thread(streamCopyFile, rp)

            results.append({"src": rp, "dst": dst, "ok": True})
        except HTTPException as he:
            results.append({"src": s, "error": he.detail, "ok": False})
        except Exception as e:
            results.append({"src": s, "error": str(e), "ok": False})

    return {"status": "ok", "results": results}


# 텔레그램 알림 API 테스트 함수
@app.get("/api/test_telegram")
async def testTelegram(request: Request, login: Any = Depends(requireLogin)):
    try:
        cfg = loadConfig() or {}
        tel = loadTelegram() or {}

        enabled = toBool(cfg.get("telegram_enabled", False))
        token   = (tel.get("telegram_bot_token") or "").strip()
        chat_id = (tel.get("telegram_chat_id") or "").strip()

        if not enabled:
            return JSONResponse(
                content={'status': 'error', 'message': '텔레그램 알림 사용이 OFF입니다. ON으로 저장 후 다시 시도하세요.'},
                status_code=400
            )
        if not token or not chat_id:
            return JSONResponse(
                content={'status': 'error', 'message': '봇 토큰 또는 채팅 ID가 비어 있습니다.'},
                status_code=400
            )

        # 실제 Telegram API 호출 (테스트용)
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        params = {"chat_id": chat_id, "text": "Live Auto Recorder 테스트 메시지입니다.", "parse_mode": "HTML"}
        r = requests.get(url, params=params, timeout=10)

        if r.status_code == 200:
            return JSONResponse(content={'status': 'success', 'message': '테스트 메시지를 전송했습니다.'})
        else:
            # 텔레그램에서 내려주는 에러 바디 그대로 전달
            return JSONResponse(
                content={'status': 'error', 'message': f"전송 실패: {r.status_code} {r.text}"},
                status_code=400
            )
    except Exception as e:
        return JSONResponse(content={'status': 'error', 'message': str(e)}, status_code=500)


# 설정 페이지 라우트
@app.get("/config", response_class=HTMLResponse)
async def configPage(request: Request, login: Any = Depends(requireLogin)):
    config_data = loadConfig()           
    request.app.state.config = config_data   
    account = loadAccount()             
    telegram = loadTelegram()

    return templates.TemplateResponse('config.html', {
        'request': request,
        'config': config_data,
        'account': account,
        'telegram': telegram,
        'program_version': PROGRAM_VERSION
    })


@app.get("/api/config")
async def get_config_api():
    return loadConfig()


@app.post("/config")
async def updateConfig(
    request: Request,
    autoRecordingMode: Optional[str] = Form(None),
    enableTray: Optional[str] = Form(None),
    minimizeToTrayOnClose: Optional[str] = Form(None),
    minimizeToTrayOnStart: Optional[str] = Form(None),
    plugin_type: Optional[str] = Form(None),
    timemachine_time_shift: Optional[int] = Form(None),
    autoPostProcessing: Optional[str] = Form(None),
    deleteAfterPostProcessing: Optional[str] = Form(None),
    removeFixedPrefix: Optional[str] = Form(None),
    moveAfterProcessingEnabled: Optional[str] = Form(None),
    moveAfterProcessing: Optional[str] = Form(None),
    postNewWindow: Optional[str] = Form(None),
    recheckInterval: Optional[int] = Form(None),
    filenamePattern: Optional[str] = Form(None),
    splitRecordingMode: Optional[str] = Form(None),
    splitPostProcessing: Optional[str] = Form(None),
    autoStopInterval: Optional[int] = Form(None),
    splitOverlapSec: Optional[int] = Form(None),
    stream_copy: Optional[str] = Form(None),
    video_codec: str = Form("libx264"),
    preset: str = Form("medium"),
    use_bitrate_mode: Optional[str] = Form(None),
    video_quality: int = Form(23),
    video_bitrate: str = Form("1000k"),
    vbv_maxrate: str = Form(""),
    vbv_bufsize: str = Form(""),
    extra_ffmpeg_options: str = Form(""),
    audio_codec: str = Form("aac"),
    audio_bitrate: str = Form("192k"),
    loginMode: Optional[str] = Form(None),
    fileManagerEnabled: Optional[str] = Form(None),
    fileManagerRoots: List[str] = Form([]),
    fileManagerMode: str = Form("blacklist"),
    fileManagerReadOnly: Optional[str] = Form(None),
    trashEnabled: Optional[str] = Form(None),
    telegram_enabled: str = Form("off"),
    telegram_bot_token: str = Form(""),
    telegram_chat_id: str = Form(""),
    discord_enabled: str = Form("off"),
    discord_webhook_url: str = Form(""),
    login: Any = Depends(requireLogin)
):
    try:
        # 1) 기존 설정 로드
        current_config = loadConfig() or {}

        # 2) 플러그인/시프트
        posted_plugin = (plugin_type or "").strip().lower() if plugin_type is not None else None
        if posted_plugin in ("basic", "timemachine_plus"):
            normalized_plugin = posted_plugin
        else:
            normalized_plugin = (current_config.get("plugin_type") or "basic")

        try:
            if timemachine_time_shift is None:
                _shift = int(current_config.get("timemachine_time_shift", 0) or 0)
            else:
                _shift = int(timemachine_time_shift or 0)
        except Exception:
            _shift = int(current_config.get("timemachine_time_shift", 0) or 0)

        normalized_shift = (
            max(0, min(10, _shift)) if normalized_plugin == "basic"
            else max(0, min(3600, _shift))
        )

        # 3) 파일매니저(웹 전용)
        normalized_roots = _normalizeAllowedRoots(fileManagerRoots)
        effective_fm_enabled = toBool(loginMode) and toBool(fileManagerEnabled)

        # 4) 분할/오버랩/오토스탑
        _split_on = toBool(splitRecordingMode) if splitRecordingMode is not None else bool(current_config.get("splitRecordingMode", False))
        try:
            if splitOverlapSec is None:
                ov = int(current_config.get("splitOverlapSec", 0) or 0)
            else:
                ov = int(splitOverlapSec or 0)
        except Exception:
            ov = int(current_config.get("splitOverlapSec", 0) or 0)
        if ov < 0: ov = 0
        if ov > 30: ov = 30
        if not _split_on:
            ov = 0

        # autoStopInterval: 분할 ON일 때만, 누락 시 기존값 유지
        try:
            if _split_on:
                _auto_stop = int(autoStopInterval) if autoStopInterval is not None else int(current_config.get("autoStopInterval", 0) or 0)
            else:
                _auto_stop = 0
        except Exception:
            _auto_stop = 0 if not _split_on else int(current_config.get("autoStopInterval", 0) or 0)

        # 5) 트레이/텔레그램
        _enable_tray   = toBool(enableTray) if enableTray is not None else bool(current_config.get("enableTray", False))
        _tray_on_close = toBool(minimizeToTrayOnClose) if minimizeToTrayOnClose is not None else bool(current_config.get("minimizeToTrayOnClose", False))
        _tray_on_start = toBool(minimizeToTrayOnStart) if minimizeToTrayOnStart is not None else bool(current_config.get("minimizeToTrayOnStart", False))
        if not _enable_tray:
            _tray_on_close = False
            _tray_on_start = False

        tel_on = toBool(telegram_enabled)

        # 6) 재탐색/파일명
        try:
            _recheck = int(recheckInterval) if recheckInterval is not None else int(current_config.get("recheckInterval", 60))
        except Exception:
            _recheck = int(current_config.get("recheckInterval", 60))
        _pattern = filenamePattern if (filenamePattern not in (None, "")) else current_config.get("filenamePattern", "[{start_time}] {safe_live_title}")

        # 7) 이동경로: 누락 시 기존값 유지(빈 문자열은 None)
        _move_path = (
            current_config.get("moveAfterProcessing")
            if moveAfterProcessing is None
            else (moveAfterProcessing or None)
        )

        # 8) 새 설정 구성(없으면 기존값 유지 원칙)
        new_config = {
            **current_config,
            "autoRecordingMode":            toBool(autoRecordingMode),
            "enableTray":                   _enable_tray,
            "minimizeToTrayOnClose":        _tray_on_close,
            "minimizeToTrayOnStart":        _tray_on_start,
            "plugin_type":                  normalized_plugin,
            "timemachine_time_shift":       normalized_shift,
            "autoPostProcessing":           toBool(autoPostProcessing),
            "deleteAfterPostProcessing":    toBool(deleteAfterPostProcessing),
            "removeFixedPrefix":            toBool(removeFixedPrefix),
            "moveAfterProcessingEnabled":   toBool(moveAfterProcessingEnabled),
            "moveAfterProcessing":          _move_path,
            "postNewWindow":                toBool(postNewWindow),
            "recheckInterval":              _recheck,
            "filenamePattern":              _pattern,
            "splitRecordingMode":           _split_on,
            "splitPostProcessing":          toBool(splitPostProcessing),
            "autoStopInterval":             _auto_stop,
            "splitOverlapSec":              ov,
            "stream_copy":                  toBool(stream_copy),
            "video_codec":                  video_codec,
            "preset":                       preset,
            "use_bitrate_mode":             toBool(use_bitrate_mode),
            "video_quality":                video_quality,
            "video_bitrate":                video_bitrate,
            "vbv_maxrate":                  vbv_maxrate,
            "vbv_bufsize":                  vbv_bufsize,
            "extra_ffmpeg_options":         extra_ffmpeg_options,
            "audio_codec":                  audio_codec,
            "audio_bitrate":                audio_bitrate,
            "telegram_enabled":             tel_on,
            "loginMode":                    toBool(loginMode),
            "fileManagerEnabled":           effective_fm_enabled,
            "fileManagerRoots":             normalized_roots,
            "fileManagerMode":              fileManagerMode if fileManagerMode in ("blacklist","whitelist") else "blacklist",
            "fileManagerReadOnly":          toBool(fileManagerReadOnly),
            "trashEnabled":                 toBool(trashEnabled),
            "discord_enabled":              toBool(discord_enabled),
            "discord_webhook_url":          discord_webhook_url.strip(),
        }

        # 9) 텔레그램 필수 체크
        if new_config.get("telegram_enabled"):
            if not telegram_bot_token.strip() or not telegram_chat_id.strip():
                error_message = "텔레그램 알림 사용 시 봇 토큰과 채팅방 ID를 모두 입력해야 합니다."
                config_data = loadConfig()
                account = loadAccount()

                return templates.TemplateResponse('config.html', {
                    'request': request,
                    'config': config_data,
                    'account': account,
                    'telegram': loadTelegram(),
                    'error_message': error_message,
                    'program_version': PROGRAM_VERSION
                }, status_code=400)


        # 10) 저장
        logger.debug("설정 저장 중...")
        saveConfig(new_config)
        request.app.state.config = new_config
        logger.debug("설정 저장 완료")

        saveTelegram({
            'telegram_bot_token': telegram_bot_token.strip(),
            'telegram_chat_id':   telegram_chat_id.strip()
        })

        if new_config.get('loginMode', False):
            account = loadAccount()
            if not account:
                return RedirectResponse(url="/register?need_account=1", status_code=303)

        return RedirectResponse(url="/", status_code=303)

    except Exception as e:
        logger.error(f"설정 저장 중 오류 발생: {e}")
        return JSONResponse(
            content={"status": "error", "message": "설정 저장 중 오류 발생: " + str(e)},
            status_code=500
        )


@app.get("/get_config")
async def get_config(request: Request):
    try:
        return {"status": "success", "config": request.app.state.config}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── #2: Discord 테스트 API ───────────────────────────────────
@app.post("/api/discord_test")
async def api_discord_test(request: Request, login: Any = Depends(requireLogin)):
    """Discord 웹훅 테스트 메시지 전송."""
    try:
        body = await request.json()
        webhook_url = (body.get("webhook_url") or "").strip()
        if not webhook_url.startswith("https://"):
            return JSONResponse(
                content={"status": "error", "message": "유효한 웹훅 URL이 아닙니다."},
                status_code=400
            )
        import requests as req_lib
        payload = {
            "embeds": [{
                "title": "🔔 Live Auto Recorder 테스트 알림",
                "description": "Discord 웹훅 설정이 정상적으로 완료되었습니다!",
                "color": 0x57F287,
                "footer": {"text": "Live Auto Recorder"},
            }]
        }
        resp = req_lib.post(webhook_url, json=payload, timeout=10)
        if resp.status_code in (200, 204):
            return {"status": "success", "message": "테스트 메시지 전송 성공"}
        else:
            return JSONResponse(
                content={"status": "error", "message": f"Discord 응답: {resp.status_code}"},
                status_code=400
            )
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)


# ── #3: 녹화 이력 API ────────────────────────────────────────
@app.get("/api/recording_history")
async def api_recording_history(
    limit: int = 50,
    channel_id: Optional[str] = None,
    event: Optional[str] = None,
    login: Any = Depends(requireLogin)
):
    """최근 녹화 이력 조회 (최신순)."""
    try:
        entries = get_history(limit=min(limit, 200), channel_id=channel_id, event=event)
        stats = get_recording_stats()
        return {"status": "success", "history": entries, "stats": stats}
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)


# ── #4: 설정 백업/복원 API ───────────────────────────────────
@app.get("/api/config_export")
async def api_config_export(login: Any = Depends(requireLogin)):
    """전체 설정 + 채널 목록 JSON 백업."""
    try:
        from starlette.responses import Response as StarletteResponse
        backup = {
            "export_version": 1,
            "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "config": loadConfig(),
            "channels": loadChannels(),
            "telegram": loadTelegram(),
        }
        content = json.dumps(backup, ensure_ascii=False, indent=2)
        filename = f"live-auto-recorder_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        return StarletteResponse(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)


@app.post("/api/config_import")
async def api_config_import(request: Request, login: Any = Depends(requireLogin)):
    """JSON 백업 파일로 설정 복원."""
    try:
        body = await request.json()
        if not isinstance(body, dict) or "config" not in body:
            return JSONResponse(
                content={"status": "error", "message": "유효하지 않은 백업 파일입니다."},
                status_code=400
            )

        # 설정 복원
        if "config" in body:
            saveConfig(body["config"])
            request.app.state.config = loadConfig()

        # 채널 복원
        if "channels" in body and isinstance(body["channels"], list):
            saveChannels(body["channels"])

        # 텔레그램 복원
        if "telegram" in body and isinstance(body["telegram"], dict):
            saveTelegram(body["telegram"])

        return {"status": "success", "message": "설정이 복원되었습니다."}
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)


# ── #5: 파일 정리 (Retention) API ────────────────────────────
@app.post("/api/file_cleanup")
async def api_file_cleanup(request: Request, login: Any = Depends(requireLogin)):
    """
    녹화 파일 정리.
    body: {
        "mode": "age" | "size",
        "age_days": int,          # age 모드: N일 이전 파일 삭제
        "max_size_gb": float,     # size 모드: 총 용량 초과 시 오래된 것부터 삭제
        "path": str,              # 대상 경로 (기본: /recordings)
        "dry_run": bool           # true면 삭제 없이 목록만 반환
    }
    """
    try:
        body = await request.json()
        mode = body.get("mode", "age")
        age_days = int(body.get("age_days", 30))
        max_size_gb = float(body.get("max_size_gb", 100))
        target_path = body.get("path", "/recordings")
        dry_run = bool(body.get("dry_run", True))

        if not os.path.isdir(target_path):
            return JSONResponse(
                content={"status": "error", "message": f"경로를 찾을 수 없습니다: {target_path}"},
                status_code=400
            )

        # 파일 수집 (영상 파일만)
        VIDEO_EXTS = {".mp4", ".mkv", ".ts", ".flv", ".avi", ".webm", ".mov"}
        files = []
        for root, dirs, filenames in os.walk(target_path):
            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in VIDEO_EXTS:
                    continue
                fpath = os.path.join(root, fname)
                try:
                    st = os.stat(fpath)
                    files.append({
                        "path": fpath,
                        "name": fname,
                        "size": st.st_size,
                        "mtime": st.st_mtime,
                    })
                except OSError:
                    continue

        # mtime 기준 정렬 (오래된 것 먼저)
        files.sort(key=lambda x: x["mtime"])

        to_delete = []
        now = time.time()

        if mode == "age":
            cutoff = now - (age_days * 86400)
            to_delete = [f for f in files if f["mtime"] < cutoff]
        elif mode == "size":
            max_bytes = max_size_gb * (1024 ** 3)
            total = sum(f["size"] for f in files)
            if total > max_bytes:
                excess = total - max_bytes
                accumulated = 0
                for f in files:
                    if accumulated >= excess:
                        break
                    to_delete.append(f)
                    accumulated += f["size"]

        # 실행
        deleted = []
        errors = []
        if not dry_run:
            for f in to_delete:
                try:
                    os.remove(f["path"])
                    deleted.append(f["name"])
                except Exception as e:
                    errors.append({"name": f["name"], "error": str(e)})

        return {
            "status": "success",
            "dry_run": dry_run,
            "mode": mode,
            "total_files": len(files),
            "total_size_gb": round(sum(f["size"] for f in files) / (1024**3), 2),
            "to_delete_count": len(to_delete),
            "to_delete_size_gb": round(sum(f["size"] for f in to_delete) / (1024**3), 2),
            "deleted": deleted,
            "errors": errors,
            "candidates": [{"name": f["name"], "size_mb": round(f["size"]/(1024**2), 1),
                           "date": datetime.fromtimestamp(f["mtime"]).strftime("%Y-%m-%d %H:%M")}
                          for f in to_delete[:50]],
        }
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)


# ── #6: WebSocket 실시간 대시보드 ────────────────────────────
from starlette.websockets import WebSocket, WebSocketDisconnect

@app.websocket("/ws/sys_metrics")
async def ws_sys_metrics(websocket: WebSocket):
    """실시간 시스템 메트릭 WebSocket (2초 간격 푸시)."""
    await websocket.accept()
    try:
        while True:
            try:
                cpu_pct = float(psutil.cpu_percent(interval=0.1))
                vm = psutil.virtual_memory()

                # 네트워크
                n1 = psutil.net_io_counters(pernic=False)
                await asyncio.sleep(0.5)
                n2 = psutil.net_io_counters(pernic=False)
                up_bps = max(0.0, float(n2.bytes_sent - n1.bytes_sent) / 0.5)
                down_bps = max(0.0, float(n2.bytes_recv - n1.bytes_recv) / 0.5)

                # 디스크
                disks = []
                try:
                    parts = psutil.disk_partitions(all=True)
                except Exception:
                    parts = []
                seen = set()
                EPHEMERAL = {"tmpfs","proc","sysfs","cgroup","cgroup2","squashfs","devpts","overlay"}
                for p in parts:
                    mp = (p.mountpoint or "").strip()
                    if not mp or mp in seen:
                        continue
                    if (p.fstype or "").lower() in EPHEMERAL and mp not in ("/", "/home", "/boot"):
                        continue
                    try:
                        u = psutil.disk_usage(mp)
                    except Exception:
                        continue
                    seen.add(mp)
                    disks.append({
                        "mountpoint": mp,
                        "label": _shortDiskLabel(p),
                        "total": int(u.total),
                        "used": int(u.used),
                        "free": int(u.free),
                        "percent": float(u.percent),
                    })

                payload = {
                    "cpu_percent": cpu_pct,
                    "cpu_name": cpu_name,
                    "mem_percent": float(vm.percent),
                    "mem_used": int(vm.used),
                    "mem_total": int(vm.total),
                    "net_up_bps": up_bps,
                    "net_down_bps": down_bps,
                    "disks": disks,
                    "ts": time.time(),
                }
                await websocket.send_json(payload)
                await asyncio.sleep(1.5)  # 총 ~2초 간격

            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.warning(f"ws_sys_metrics error: {e}")
                await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


# runUvicorn 서버실행 함수
async def runUvicorn():
    try:
        config_data = loadConfig()  
        port = config_data.get('port', 5000)  # port 값 불러오고, 없으면 기본값 5000 사용

        # Uvicorn 서버를 비동기적으로 실행
        config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="debug")
        server = uvicorn.Server(config)
        logger.debug(f"Uvicorn 서버 시작 - 포트 {port}")
        await server.serve()
    except Exception as e:
        logger.error(f"runUvicorn 중 오류 발생: {e}")
        raise e


# 비동기로 서버 실행 함수 
async def runAutomodeServer():
    try:
        # 자동녹화는 lifespan에서 시작하므로 여기서는 서버만 띄움
        logger.debug("runUvicorn 호출")
        await runUvicorn()

    except Exception as e:
        logger.error(f"서버 실행 중 오류 발생: {e}")


# 트레이 아이콘 기동 함수 (수정본)
def startWebTray():
    try:
        cfg = loadConfig() or {}
        enable_tray = bool(cfg.get("enableTray", False))
        if not enable_tray:
            return

        # pystray/Pillow 사용 가능 여부 확인
        if pystray is None or Image is None:
            logger.warning("최소화 트레이 기능이 활성화 되었지만 pystray 또는 Pillow가 설치되지 않았습니다.")
            return

        # Windows 권장
        if os.name != "nt":
            logger.warning("최소화 트레이 기능이 활성화 되었지만 현재 OS에서 트레이가 보장되지 않습니다.")

        # 모듈 네임스페이스 별칭 (함수 내부 re-import 불필요)
        Menu     = pystray.Menu
        MenuItem = pystray.MenuItem
        Icon     = pystray.Icon

        icon_path = os.path.join(BASE_DIR, "templates", "static", "img", "tray_icon.png")

        try:
            img = Image.open(icon_path)
        except Exception:
            # 못 열면 투명 64x64 placeholder
            img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            logger.warning(f"tray icon open failed: {icon_path}")

        def _open_browser():
            import webbrowser
            try:
                webbrowser.open(getBaseUrl())
            except Exception:
                pass

        def _start_all():
            import requests
            try:
                requests.post(f"{getBaseUrl()}/api/start_all_recording",
                              json={"is_user_request": True}, timeout=5)
            except Exception:
                pass

        def _stop_all():
            import requests
            try:
                requests.post(f"{getBaseUrl()}/api/stop_all_recording",
                              json={"is_user_request": True}, timeout=5)
            except Exception:
                pass

        def _on_quit(icon, item):
            icon.visible = False
            os._exit(0)

        menu = Menu(
            MenuItem("브라우저 열기", _open_browser),
            Menu.SEPARATOR,
            MenuItem("모두 녹화 시작", _start_all),
            MenuItem("모두 녹화 중지", _stop_all),
            Menu.SEPARATOR,
            MenuItem("종료", _on_quit),
        )

        # 현재 스레드 블록하지 않음
        Icon("Live Auto Recorder", img, "Live Auto Recorder", menu).run_detached()
        logger.debug("Web tray icon started (detached).")

    except Exception as e:
        logger.warning(f"트레이 초기화 중 예외: {e}")



if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)

    config_data = loadConfig() 
    port = config_data.get('port', 5000) 

    internal_ip, local_ip, external_ip = getAddresses()

    # 프로그램 이름과 버전 출력
    logger.info(f"Starting {PROGRAM_NAME} version {PROGRAM_VERSION}")

    # 프로그램 첫 실행 시 FFmpeg와 Streamlink 경로 확인
    checkRequiredPaths()

    if internal_ip and "오류" not in internal_ip:
        logger.info(f"* 로컬호스트 주소로 접속 http://{internal_ip}:{port}")

    if local_ip and "오류" not in local_ip:
        logger.info(f"* 내부 사설 IP 주소로 접속 http://{local_ip}:{port}")

    if external_ip and "오류" not in external_ip:
        logger.info(f"* 공인 IP 주소로 접속 http://{external_ip}:{port}")

    # 먼저 트레이를 비차단 방식으로 띄운 뒤,
    if config_data.get("enableTray", False):
        startWebTray()
        try:
            minimizeConsole()
        except Exception:
            pass

    # 기존과 동일하게 비동기 서버를 실행
    asyncio.run(runAutomodeServer())