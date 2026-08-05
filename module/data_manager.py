from __future__ import annotations
from module.log_setup import get_logger
logger = get_logger("data_manager")

import json
import os
import sys
import requests
import hashlib
import glob
import secrets
import asyncio
import time
import shutil
import threading
import contextlib  
import base64
from threading import RLock
from datetime import datetime
from cryptography.fernet import Fernet
from typing import Dict, Set, Optional

from module.common_errors import printOnce

base_directory = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONFIG_PATH = os.path.join(base_directory, 'json', 'config.json')
CHANNELS_PATH = os.path.join(base_directory, 'json', 'channels.json')
COOKIE_PATH = os.path.join(base_directory, 'json', 'cookie.json')
yCOOKIE_PATH = os.path.join(base_directory, 'json', 'ycookie.txt')
LOGIN_PATH = os.path.join(base_directory, 'json', 'login.json')
TELEGRAM_PATH = os.path.join(base_directory, 'json', 'telegram.json')

# 전역 asyncio 락 
move_async_lock = asyncio.Lock()

TRUE_SET  = {"1","true","t","yes","y","on"}
FALSE_SET = {"0","false","f","no","n","off",""}

ALLOWED_KEYS = {
    "platform", "id", "name", "output_dir",
    "quality", "extension", "record_enabled",
    "recordWatchParty", "watchPartyExcludeTags"}


def toBool(v, *, default=False):
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        s = v.strip().lower()
        if s in TRUE_SET:
            return True
        if s in FALSE_SET:
            return False
        return default
    return bool(v)


def canonJson(obj) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    except Exception:
        return ""


def readJsonSafe(path: str, default):
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            txt = f.read()
        if not txt.strip():
            recovered = _restoreFromBak(path, default)
            if recovered is not default:
                writeJsonSafe(path, recovered)
            return recovered
        return json.loads(txt)
    except Exception:
        recovered = _restoreFromBak(path, default)
        if recovered is not default:
            writeJsonSafe(path, recovered)
        return recovered


def writeJsonSafe(path: str, data) -> bool:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    current = None
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                current = json.load(f)
        except Exception:
            # 손상이면 .bak로 밀어두고 계속 진행
            try:
                shutil.copyfile(path, path + ".corrupt.bak")
            except Exception:
                pass
            current = None

    if current is not None and canonJson(current) == canonJson(data):
        # 동일 내용 → 저장하지 않음
        return False

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        f.flush()
        os.fsync(f.fileno())

    # 기존이 있으면 .bak로
    try:
        if os.path.exists(path):
            shutil.copyfile(path, path + ".bak")
    except Exception:
        pass

    os.replace(tmp, path)
    return True


def _restoreFromBak(path: str, default):
    bak = path + ".bak"
    try:
        if os.path.exists(bak):
            with open(bak, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def filterChannelKeys(ch: dict, allowed: set) -> dict:
    return {k: v for k, v in ch.items() if k in allowed}


def normalizeChannelsList(lst: list[dict]) -> list[dict]:
    def _norm_one(d):
        out = dict(d)

        # 0) platform/id/name 기본 정규화
        plat = str(out.get("platform", "")).strip().lower()
        if plat not in ("chzzk", "youtube"):
            logger.warning(f"지원하지 않는 platform 스킵: {plat!r}")
            return None
        out["platform"] = plat

        cid = str(out.get("id", "")).strip()
        if not cid:
            logger.warning("빈 채널 id 스킵")
            return None
        out["id"] = cid

        out["name"] = str(out.get("name", "")).strip()

        # 1) 타입 보정
        out["record_enabled"]    = bool(out.get("record_enabled", False))
        out["recordWatchParty"]  = bool(out.get("recordWatchParty", False))
        out["quality"]           = str(out.get("quality", "best"))
        out["extension"]         = str(out.get("extension", "mp4"))

        # 2) watchPartyExcludeTags 정규화(문자열/배열 허용, 공백·대소문자 중복 제거)
        raw_tags = out.get("watchPartyExcludeTags")
        if isinstance(raw_tags, str):
            parts = [s.strip() for s in raw_tags.split(",")]
        elif isinstance(raw_tags, list):
            parts = [str(s).strip() for s in raw_tags]
        else:
            parts = []
        seen = set(); norm_tags = []
        for s in parts:
            key = s.lower()
            if s and key not in seen:
                seen.add(key); norm_tags.append(s)
        out["watchPartyExcludeTags"] = norm_tags

        # 3) 유튜브는 같이보기 옵션 강제 비활성 (데이터는 유지)
        if plat != "chzzk":
            out["recordWatchParty"] = False

        return out

    # 4) 개별 정규화
    items = []
    for x in (lst or []):
        fixed = _norm_one(x)
        if fixed is not None:
            items.append(fixed)

    # 5) 중복 병합: 먼저 등장한 항목 우선, 태그는 합집합
    merged = []
    seen_keys = {}
    for ch in items:
        key = (ch["platform"], ch["id"])
        if key in seen_keys:
            i = seen_keys[key]
            # 태그 합집합
            a = merged[i].get("watchPartyExcludeTags") or []
            b = ch.get("watchPartyExcludeTags") or []
            sset = set()
            merged_tags = []
            for s in a + b:
                k = s.lower()
                if k not in sset:
                    sset.add(k); merged_tags.append(s)
            merged[i]["watchPartyExcludeTags"] = merged_tags

            # name/output_dir 등은 기존 유지(필요시 아래처럼 비어있으면 갱신)
            if not merged[i].get("name") and ch.get("name"):
                merged[i]["name"] = ch["name"]
            # 그 외 필드 병합 규칙 필요하면 여기에 추가
        else:
            seen_keys[key] = len(merged)
            merged.append(ch)

    return merged


class RecorderManager:
    # A) UI/알림 상태
    status_recording      : Dict[str, bool]   = {}
    status_reserved       : Dict[str, bool]   = {}
    status_last_notified  : Dict[str, str]    = {}     # 알림 상태 캐시
    status_watchparty_off : Set[str]          = set()  # 같이보기 OFF 알림 플래그

    # B) 사용자 의도/요청
    is_user_stopped       : Set[str]          = set()  # 사용자 '중지' 의도

    # C) 진입/중복 가드
    guard_starting        : Set[str]          = set()  # 시작 진입 가드(원자성)

    # D) 동시성/자원
    tasks_worker          : Dict[str, asyncio.Task]                 = {}
    tasks_process         : Dict[str, asyncio.subprocess.Process]   = {}

    # E) 녹화 메타
    recording_start_time  : Dict[str, float]  = {}
    recording_filename    : Dict[str, str]    = {}
    recording_postproc_inflight : Set[str]    = set()

    # F) 헬스/왓치독 메타(관찰 전용)
    watchdog_last_beat        : Dict[str, float] = {}
    watchdog_restart_attempts : Dict[str, int]   = {}
    watchdog_backoff_until    : Dict[str, float] = {}

    # G) 채널 목록(프로세스 전역 메모리 캐시/레퍼런스)
    _channels_cache_lock = threading.RLock()
    _channels_cache: list = []
    _channels_ref = None             # 외부(ref)로 직접 관리되는 리스트를 가리킬 수 있음
    _channels_lock_ref = None        # 외부 락 레퍼런스

    def __init__(self):
        self._lock = threading.RLock()

    # 채널 목록 접근(기존 호환)
    @classmethod
    def setChannelsRef(cls, ref):
        cls._channels_ref = ref

    @classmethod
    def setChannelsLockRef(cls, ref):
        cls._channels_lock_ref = ref

    @classmethod
    def getChannelsLockRef(cls):
        return cls._channels_lock_ref

    @classmethod
    def getChannels(cls) -> list:
        # 1) 캐시 우선
        with cls._channels_cache_lock:
            if cls._channels_cache:
                return list(cls._channels_cache)

        # 2) 레퍼런스 포인터 사용
        if cls._channels_ref is not None:
            lock = cls._channels_lock_ref

            try:
                import asyncio as _aio
                if isinstance(lock, _aio.Lock):
                    return list(cls._channels_ref)
            except Exception:
                pass
            # 일반 락이면 잡고 반환, 실패해도 복사본 반환
            if lock is not None:
                try:
                    with lock:
                        return list(cls._channels_ref)
                except Exception:
                    return list(cls._channels_ref)
            return list(cls._channels_ref)

        # 3) 마지막 폴백: 디스크 → 캐시 적재
        try:
            data = loadChannels() or []
        except Exception:
            data = []
        with cls._channels_cache_lock:
            cls._channels_cache = list(data)
        return list(cls._channels_cache)

    @classmethod
    def setChannels(cls, channels: list) -> None:
        with cls._channels_cache_lock:
            cls._channels_cache = list(channels or [])


    # A) UI/알림 상태
    def get_status_recording(self, channel_id: str) -> bool:
        with self._lock:
            return bool(self.__class__.status_recording.get(channel_id, False))

    def set_status_recording(self, channel_id: str, value: bool) -> None:
        with self._lock:
            self.__class__.status_recording[channel_id] = bool(value)

    def get_status_reserved(self, channel_id: str) -> bool:
        with self._lock:
            return bool(self.__class__.status_reserved.get(channel_id, False))

    def set_status_reserved(self, channel_id: str, value: bool) -> None:
        with self._lock:
            self.__class__.status_reserved[channel_id] = bool(value)

    # watch party off 알림 플래그
    def is_watch_party_off_notified(self, channel_id: str) -> bool:
        with self._lock:
            return channel_id in self.__class__.status_watchparty_off

    def set_watch_party_off_notified(self, channel_id: str, value: bool) -> None:
        with self._lock:
            if value:
                self.__class__.status_watchparty_off.add(channel_id)
            else:
                self.__class__.status_watchparty_off.discard(channel_id)

    def reset_watch_party_off_notified(self, channel_id: str) -> None:
        with self._lock:
            self.__class__.status_watchparty_off.discard(channel_id)

    # B) 사용자 의도/요청
    def get_is_user_stopped(self, channel_id: str) -> bool:
        with self._lock:
            return channel_id in self.__class__.is_user_stopped

    def set_is_user_stopped(self, channel_id: str, value: bool) -> None:
        with self._lock:
            if value:
                self.__class__.is_user_stopped.add(channel_id)
            else:
                self.__class__.is_user_stopped.discard(channel_id)

    # C) 진입/중복 가드
    def guard_try_acquire_start(self, channel_id: str) -> bool:
        with self._lock:
            if channel_id in self.__class__.guard_starting:
                return False
            self.__class__.guard_starting.add(channel_id)
            return True

    def guard_release_start(self, channel_id: str) -> None:
        with self._lock:
            self.__class__.guard_starting.discard(channel_id)

    # D) 동시성/자원 (태스크/프로세스)
    def get_tasks_worker(self, channel_id: str) -> Optional[asyncio.Task]:
        with self._lock:
            return self.__class__.tasks_worker.get(channel_id)

    def set_tasks_worker(self, channel_id: str, task: asyncio.Task) -> None:
        with self._lock:
            self.__class__.tasks_worker[channel_id] = task

    def clear_tasks_worker(self, channel_id: str) -> None:
        with self._lock:
            self.__class__.tasks_worker.pop(channel_id, None)

    def get_tasks_process(self, channel_id: str) -> Optional[asyncio.subprocess.Process]:
        with self._lock:
            return self.__class__.tasks_process.get(channel_id)

    def set_tasks_process(self, channel_id: str, proc: asyncio.subprocess.Process) -> None:
        with self._lock:
            self.__class__.tasks_process[channel_id] = proc

    def clear_tasks_process(self, channel_id: str) -> None:
        with self._lock:
            self.__class__.tasks_process.pop(channel_id, None)

    # E) 녹화 메타
    def recording_set_start_time(self, channel_id: str, ts: Optional[float] = None) -> None:
        with self._lock:
            self.__class__.recording_start_time[channel_id] = ts if ts is not None else time.time()

    def recording_remove_start_time(self, channel_id: str) -> None:
        with self._lock:
            self.__class__.recording_start_time.pop(channel_id, None)

    def recording_set_filename(self, channel_id: str, path: str) -> None:
        with self._lock:
            self.__class__.recording_filename[channel_id] = path

    def recording_remove_filename(self, channel_id: str) -> None:
        with self._lock:
            self.__class__.recording_filename.pop(channel_id, None)

    def recording_add_postproc(self, channel_id: str) -> bool:
        with self._lock:
            if channel_id in self.__class__.recording_postproc_inflight:
                return False
            self.__class__.recording_postproc_inflight.add(channel_id)
            return True

    def recording_remove_postproc(self, channel_id: str) -> None:
        with self._lock:
            self.__class__.recording_postproc_inflight.discard(channel_id)

    # 파일 지문 기반 중복 가드
    def _compute_file_fingerprint(self, src_path: str, head_bytes: int = 65536) -> str:
        try:
            p = os.path.abspath(src_path).lower()
            st = os.stat(p)
            size = st.st_size
            mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))

            h = hashlib.md5()
            with open(p, "rb") as f:
                h.update(f.read(head_bytes))
            head_md5 = h.hexdigest()

            key = f"{p}|{size}|{mtime_ns}|{head_md5}"
            fp = hashlib.sha1(key.encode("utf-8")).hexdigest()
            return fp

        except Exception:
            # 지문 계산 실패 시 경로 기반으로만
            try:
                return hashlib.sha1(os.path.abspath(src_path).encode("utf-8")).hexdigest()
            except Exception:
                return f"fp:{src_path}"

    # 최근 본 지문 캐시(지문 -> last_ts)
    _postproc_seen_fps: Dict[str, float] = {}

    def postproc_try_acquire_source(self, src_path: str, ttl_sec: int = 1800) -> bool:
        fp = self._compute_file_fingerprint(src_path)
        now = time.time()

        # 만료 정리
        for k, ts in list(self.__class__._postproc_seen_fps.items()):
            if (now - ts) > ttl_sec:
                self.__class__._postproc_seen_fps.pop(k, None)

        if fp in self.__class__._postproc_seen_fps:
            return False

        self.__class__._postproc_seen_fps[fp] = now

        return True

    # F) 헬스/왓치독
    def watchdog_beat(self, channel_id: str) -> None:
        with self._lock:
            self.__class__.watchdog_last_beat[channel_id] = time.monotonic()

    def watchdog_set_backoff(self, channel_id: str, until_ts: float, attempts: int) -> None:
        with self._lock:
            self.__class__.watchdog_backoff_until[channel_id] = until_ts
            self.__class__.watchdog_restart_attempts[channel_id] = attempts

    def get_watchdog_last_beat(self, channel_id: str) -> Optional[float]:
        with self._lock:
            return self.__class__.watchdog_last_beat.get(channel_id)

    def get_watchdog_backoff_until(self, channel_id: str) -> float:
        with self._lock:
            return float(self.__class__.watchdog_backoff_until.get(channel_id, 0.0))

    def get_watchdog_restart_attempts(self, channel_id: str) -> int:
        with self._lock:
            return int(self.__class__.watchdog_restart_attempts.get(channel_id, 0))

    def watchdog_reset_backoff(self, channel_id: str) -> None:
        with self._lock:
            self.__class__.watchdog_backoff_until[channel_id] = 0.0
            self.__class__.watchdog_restart_attempts[channel_id] = 0

    def get_recording_filename(self, channel_id: str):
        with self._lock:
            return self.__class__.recording_filename.get(channel_id)

    def get_recording_start_ts(self, channel_id: str):
        with self._lock:
            return self.__class__.recording_start_time.get(channel_id)

    def get_recording_start_time(self, channel_id: str):
        ts = self.get_recording_start_ts(channel_id)
        try:
            from datetime import datetime
            return datetime.fromtimestamp(float(ts)) if ts else None
        except Exception:
            return None

    # G) 백워드 호환 래퍼
    def get_recording_status(self, channel_id: str) -> bool:
        return self.get_status_recording(channel_id)

    def set_recording_status(self, channel_id: str, value: bool) -> None:
        self.set_status_recording(channel_id, value)

    def get_reserved_recording(self, channel_id: str) -> bool:
        return self.get_status_reserved(channel_id)

    def set_reserved_recording(self, channel_id: str, value: bool) -> None:
        self.set_status_reserved(channel_id, value)

    # 사용자 중지
    def is_stop_requested(self, channel_id: str) -> bool:
        return self.get_is_user_stopped(channel_id)

    def add_stop_requested_channel(self, channel_id: str) -> None:
        self.set_is_user_stopped(channel_id, True)

    def remove_stop_requested_channel(self, channel_id: str) -> None:
        self.set_is_user_stopped(channel_id, False)

    def recording_get_filename(self, channel_id: str):
        return self.get_recording_filename(channel_id)

    # H) watchdog 호환 래퍼/로직 추가
    def watchdog_get_last_beat(self, channel_id: str):
        # loop_watchdog 호환용 별칭
        return self.get_watchdog_last_beat(channel_id)

    # 워커 태스크
    def get_worker_task(self, channel_id: str):
        return self.get_tasks_worker(channel_id)

    def set_worker_task(self, channel_id: str, task: asyncio.Task):
        self.set_tasks_worker(channel_id, task)

    def clear_worker_task(self, channel_id: str):
        self.clear_tasks_worker(channel_id)

    # 시작 가드
    def try_acquire_start(self, channel_id: str) -> bool:
        return self.guard_try_acquire_start(channel_id)

    def release_start(self, channel_id: str) -> None:
        self.guard_release_start(channel_id)

    # 프로세스
    def set_recording_process(self, channel_id: str, proc: asyncio.subprocess.Process) -> None:
        self.set_tasks_process(channel_id, proc)

    def get_recording_process(self, channel_id: str) -> Optional[asyncio.subprocess.Process]:
        return self.get_tasks_process(channel_id)

    def remove_recording_process(self, channel_id: str) -> None:
        self.clear_tasks_process(channel_id)

    # 시작 시간/파일명
    def set_recording_start_time(self, channel_id: str) -> None:
        self.recording_set_start_time(channel_id)

    def remove_recording_start_time(self, channel_id: str) -> None:
        self.recording_remove_start_time(channel_id)

    def set_recording_filename(self, channel_id: str, path: str) -> None:
        self.recording_set_filename(channel_id, path)

    def remove_recording_filename(self, channel_id: str) -> None:
        self.recording_remove_filename(channel_id)

    # 후처리 큐(기존 명)
    def add_processed_channel(self, channel_id: str) -> None:
        self.recording_add_postproc(channel_id)

    def remove_processed_channel(self, channel_id: str) -> None:
        self.recording_remove_postproc(channel_id)


    def watchdog_increase_backoff(self, channel_id: str) -> int:
        # 재시도 카운터 1 증가 + 백오프 until 기록, 호출자는 attempts만 쓰므로 반환
        with self._lock:
            cur = int(self.__class__.watchdog_restart_attempts.get(channel_id, 0)) + 1
            self.__class__.watchdog_restart_attempts[channel_id] = cur
            delay = min(600, 10 * cur * cur)
            self.__class__.watchdog_backoff_until[channel_id] = time.monotonic() + delay
            return cur


    # 채널 워커 제거
    async def force_terminate_worker(self, channel_id: str, timeout: float = 5.0) -> bool:
        with self._lock:
            task = self.__class__.tasks_worker.get(channel_id)

        if not task:
            return True

        if task.done():
            self.clear_tasks_worker(channel_id)
            return True

        try:
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=timeout)
            except asyncio.TimeoutError:
                pass
        except Exception:
            pass
        finally:
            self.clear_tasks_worker(channel_id)

        return True



    # 녹화 경과 시간 계산 함수 
    def get_recording_duration(self, channel_id: str) -> str:
        with self._lock:
            start_ts = self.__class__.recording_start_time.get(channel_id)

        if not start_ts:
            return "00:00:00"

        try:
            elapsed = int(time.time() - float(start_ts))
            if elapsed < 0:
                elapsed = 0
        except Exception:
            return "00:00:00"

        h, r = divmod(elapsed, 3600)
        m, s = divmod(r, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"


# alias 연결 
last_notified_state = RecorderManager.status_last_notified


# 계정 불러오기 함수
def loadAccount():
    if os.path.exists(LOGIN_PATH):
        with open(LOGIN_PATH, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                # username과 password가 None이면 계정이 없는 것으로 처리
                if not data.get('username') or not data.get('password'):
                    return None
                return {
                    'username': data.get('username'),
                    'password': data.get('password'),
                    'secret_key': data.get('secret_key', secrets.token_hex(32))  # 없으면 생성
                }
            except json.JSONDecodeError as e:
                logger.error(f"{LOGIN_PATH} 파일을 읽는 중 오류가 발생했습니다: {e}")
                return None
    return None


# 계정 저장 함수
def saveAccount(account):
    disk = readJsonSafe(LOGIN_PATH, {})
    if not isinstance(disk, dict):
        disk = {}
    data = {
        **disk,
        'username': account.get('username'),
        'password': account.get('password'),
        'secret_key': disk.get('secret_key', secrets.token_hex(32))
    }

    writeJsonSafe(LOGIN_PATH, data)


# channels.json 로드 함수 (유튜브와 치지직을 통합)
def loadChannels() -> list[dict]:
    raw = readJsonSafe(CHANNELS_PATH, [])
    if not isinstance(raw, list):
        raw = []
    cleaned = [filterChannelKeys(ch, ALLOWED_KEYS) for ch in raw]
    # 정렬은 normalizeChannelsList 내부에서 수행
    return normalizeChannelsList(cleaned)


# channels.json 저장 함수 (유튜브와 치지직 통합)
def saveChannels(data: list[dict]):
    try:
        cleaned = [filterChannelKeys(ch, ALLOWED_KEYS) for ch in (data or [])]
        norm = normalizeChannelsList(cleaned) 
        changed = writeJsonSafe(CHANNELS_PATH, norm)
        if changed:
            logger.debug(f"{CHANNELS_PATH} 저장 완료.")
            # ★ 실제 파일 변경이 있었을 때만 런타임 캐시 동기화
            try:
                RecorderManager.setChannels(norm)
            except Exception as e:
                logger.warning(f"setChannels 동기화 실패(무시): {e}")
    except Exception as e:
        logger.error(f"{CHANNELS_PATH} 파일 저장 오류: {e}")


# cookie.json 전용 로드 함수
def loadCookies():
    data = readJsonSafe(COOKIE_PATH, {})
    return data if isinstance(data, dict) else {}


# cookie.json 전용 저장 함수
def saveCookies(data):
    try:
        changed = writeJsonSafe(COOKIE_PATH, data or {})
        if changed:
            logger.debug(f"{COOKIE_PATH} 저장 완료.")
    except Exception as e:
        logger.error(f"{COOKIE_PATH} 저장 오류: {e}")


# config.json 파일에서 데이터를 불러오는 함수
def loadConfig():
    # 기본값
    defaults = {
        "telegram_enabled": False,
        "autoRecordingMode": False,
        "plugin_type": "basic",
        "timemachine_time_shift": 0,
        "autoPostProcessing": True,
        
        "deleteAfterPostProcessing": True,
        "removeFixedPrefix": True,
        "moveAfterProcessingEnabled": False,
        "moveAfterProcessing": "",
        "postNewWindow": False,
        "recheckInterval": 60,
        "filenamePattern": "[{start_time}] {channel_name} {safe_live_title} {record_quality}{frame_rate}{file_extension}",
        "splitRecordingMode": False,
        "splitPostProcessing": True,
        "autoStopInterval": 0,
        "splitOverlapSec": 0,
        "stream_copy": True,
        "video_codec": "libx264",
        "preset": "fast",
        "use_bitrate_mode": True,
        "video_quality": 33,
        "video_bitrate": "1000k",
        "vbv_maxrate": "",
        "vbv_bufsize": "",
        "audio_codec": "aac",
        "audio_bitrate": "192k",
        "extra_ffmpeg_options": "",
        "loginMode": False,
        "port": 5000,
        "enableTray": False,
        "minimizeToTrayOnClose": False,
        "minimizeToTrayOnStart": False,
        "fileManagerEnabled": False,
        "fileManagerRoots": [],
        "fileManagerMode": "blacklist",
        "fileManagerReadOnly": False,
        "trashEnabled": False,
        "discord_enabled": False,
        "discord_webhook_url": "",
    }

    data = readJsonSafe(CONFIG_PATH, {})
    if not isinstance(data, dict):
        data = {}

    merged = {**defaults, **data}

    # 플러그인/타임시프트 정규화
    raw_plugin = str((merged.get("plugin_type") or "basic")).strip().lower()

    # 허용값만 인정 (오직 basic, timemachine_plus)
    if raw_plugin not in ("basic", "timemachine_plus"):
        raw_plugin = "basic"  # 레거시/이상값은 기본값으로 정리

    merged["plugin_type"] = raw_plugin

    # 플러그인에 따라 시프트 허용범위만 클램프
    try:
        _shift = int(merged.get("timemachine_time_shift", 0) or 0)
    except Exception:
        _shift = 0

    merged["timemachine_time_shift"] = (
        max(0, min(3600, _shift)) if raw_plugin == "timemachine_plus"
        else max(0, min(10, _shift))
    )

    # 분할녹화 오버랩 정규화
    try:
        ov = int(merged.get("splitOverlapSec", 0) or 0)
    except Exception:
        ov = 0
    ov = max(0, min(30, ov))
    if not bool(merged.get("splitRecordingMode", False)):
        ov = 0

    merged["splitOverlapSec"] = ov
    merged["splitPostProcessing"] = bool(merged.get("splitPostProcessing", True))

    # 트레이 옵션 의존성 보정
    enable_tray = bool(merged.get("enableTray", False))
    if not enable_tray:
        merged["minimizeToTrayOnClose"] = False
        merged["minimizeToTrayOnStart"] = False

    # 파일매니저 정규화
    roots = merged.get("fileManagerRoots", [])
    if isinstance(roots, str):
        roots = [roots]
    elif not isinstance(roots, list):
        roots = []
    merged["fileManagerRoots"] = [str(p).strip() for p in roots if str(p).strip()]

    mode = str(merged.get("fileManagerMode", "blacklist")).lower()
    if mode not in ("blacklist", "whitelist"):
        mode = "blacklist"
    merged["fileManagerMode"] = mode

    # loginMode가 꺼져 있으면 fileManagerEnabled는 항상 False
    merged["fileManagerEnabled"] = bool(merged.get("loginMode", False)) and bool(merged.get("fileManagerEnabled", False))
    merged["fileManagerReadOnly"] = bool(merged.get("fileManagerReadOnly", False))
    merged["trashEnabled"] = bool(merged.get("trashEnabled", False))

    if merged.get("moveAfterProcessing") is None:
        merged["moveAfterProcessing"] = ""

    # 기타 안전 보정
    try:
        merged["recheckInterval"] = int(merged.get("recheckInterval", 60))
    except Exception:
        merged["recheckInterval"] = 60

    try:
        merged["port"] = int(merged.get("port", 5000))
    except Exception:
        merged["port"] = 5000

    merged["telegram_enabled"] = bool(merged.get("telegram_enabled", False))
    merged["discord_enabled"] = bool(merged.get("discord_enabled", False))

    return merged


# config.json 파일에서 데이터를 저장하는 함수
def saveConfig(data):
    try:
        disk = readJsonSafe(CONFIG_PATH, {})
        if not isinstance(disk, dict):
            disk = {}
        merged = {**disk, **(data or {})}
        changed = writeJsonSafe(CONFIG_PATH, merged)
        if changed:
            logger.debug(f"{CONFIG_PATH} 저장 완료.")
        return merged
    except Exception as e:
        logger.error(f"{CONFIG_PATH} 저장 오류: {e}")
        return data or {}



# youtube용 최소 CONSENT 쿠키 파일을 저장/보장
def ysaveCookies(path: Optional[str] = None) -> str:
    target = path or yCOOKIE_PATH
    os.makedirs(os.path.dirname(target), exist_ok=True)
    content = (
        "# Netscape HTTP Cookie File\n"
        ".youtube.com\tTRUE\t/\tTRUE\t4102444800\tCONSENT\tYES+cb.202103\n"
    )
    with open(target, "w", encoding="utf-8") as f:
        f.write(content)
    return target


# ycookie.txt 불러오는 함수 (유튜브 레코더용)
def yloadCookies() -> Optional[str]:
    # yCOOKIE_PATH: "C:/Live Auto Recorder/json/ycookie.txt" 같은 경로
    if not os.path.exists(yCOOKIE_PATH):
        logger.info(f"{yCOOKIE_PATH} 파일이 없으므로 새로 생성합니다.")
        with open(yCOOKIE_PATH, 'w', encoding='utf-8') as f:
            f.write("# Netscape HTTP Cookie File\n")
        return None  # 쿠키 파일을 막 생성했으니 내용은 아직 유효하지 않을 수 있음
    
    # 파일이 존재하면, 경로만 반환
    return yCOOKIE_PATH


# 암호화 생성 함수
def get_encryption_key():
    account = loadAccount()
    if account and account.get('secret_key'):
        key_bytes = account['secret_key'].encode('utf-8')
        key_bytes = (key_bytes * (32 // len(key_bytes) + 1))[:32]
        return base64.urlsafe_b64encode(key_bytes)
    else:
        return Fernet.generate_key()


# telegram.json 불러오기 함수
def loadTelegram():
    if os.path.exists(TELEGRAM_PATH):
        try:
            with open(TELEGRAM_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data
        except Exception as e:
            logger.error(f"telegram.json 읽기 오류: {e}")
            return {}
    return {}


# telegram.json 저장 함수
def saveTelegram(data):
    try:
        disk = readJsonSafe(TELEGRAM_PATH, {})
        if not isinstance(disk, dict):
            disk = {}
        merged = {**disk, **(data or {})}
        changed = writeJsonSafe(TELEGRAM_PATH, merged)
        if changed:
            logger.debug("telegram.json 저장 완료")
    except Exception as e:
        logger.error(f"telegram.json 저장 오류: {e}")



# 텔레그램 알림 전송 함수 
def sendTelegram(message: str):
    # 함수 내부에서 config 불러오기
    config_data = loadConfig()
    # telegram_enabled가 False면 바로 return
    if not config_data.get("telegram_enabled", False):
        return

    telegram_data = loadTelegram()  
    bot_token = telegram_data.get("telegram_bot_token", "")
    chat_id = telegram_data.get("telegram_chat_id", "")
    if not bot_token or not chat_id:
        logger.error("Telegram 봇 토큰이나 채팅 ID가 설정되어 있지 않습니다.")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    params = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            logger.info("Telegram 알림 전송 성공.")
        else:
            logger.error(f"Telegram 알림 전송 실패: {response.status_code} {response.text}")
    except Exception as e:
        logger.error(f"Telegram 알림 전송 중 오류: {e}")



# 파일명 중복 방지 함수
def uniqueFilename(output_dir, filename, add_suffix=True):
    base, ext = os.path.splitext(filename)
    counter = 1
    unique_filename = filename if not add_suffix else f"{base} ({counter}){ext}"

    while os.path.exists(os.path.join(output_dir, unique_filename)):
        counter += 1
        unique_filename = f"{base} ({counter}){ext}"

    return unique_filename


# 후처리 후 파일 이동 함수
async def moveDirectory(file_path, destination_directory):
    loop = asyncio.get_running_loop()

    async with move_async_lock:
        def _do_move():
            try:
                if not os.path.exists(file_path):
                    logger.warning(f"원본 파일 {file_path}가 존재하지 않습니다. 이동 작업을 건너뜁니다.")
                    return

                if not os.path.exists(destination_directory):
                    os.makedirs(destination_directory)

                base_name = os.path.basename(file_path)
                name, ext = os.path.splitext(base_name)
                destination_path = os.path.join(destination_directory, base_name)

                counter = 1
                # 동일한 파일명이 존재하는지 확인하고, 존재하면 새로운 파일명 생성
                while os.path.exists(destination_path):
                    new_name = f"{name}({counter}){ext}"
                    destination_path = os.path.join(destination_directory, new_name)
                    counter += 1

                shutil.move(file_path, destination_path)
                logger.info(f"파일 {file_path}가 {destination_path}로 이동되었습니다.")
            except Exception as e:
                logger.info(f"파일 {file_path}를 {destination_directory}로 이동하는 중 오류 발생: {e}")
                raise

        await loop.run_in_executor(None, _do_move)


def getBaseUrl():
    config_data = loadConfig()
    port = config_data.get('port', 5000)  # 기본값은 5000
    return f"http://127.0.0.1:{port}"


# ffmpeg 경로를 가져오는 함수
def getFFmpeg():
    if os.name == 'nt':  # Windows
        ffmpeg_path = os.path.join(base_directory, 'dependent', 'ffmpeg', 'bin', 'ffmpeg.exe')
    else:
        ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path and os.path.exists(ffmpeg_path):
        printOnce("dep:ffmpeg:ok", f"[INFO] FFmpeg가 '{ffmpeg_path}' 경로에 있습니다.")
        return ffmpeg_path
    else:
        printOnce("dep:ffmpeg:err", "[ERROR] FFmpeg를 찾을 수 없습니다. 설치 후 PATH가 올바른지 확인해 주세요.")
        sys.exit(1)


# ffprobe 경로를 가져오는 함수
def getFFprobe():
    if os.name == 'nt':  # Windows
        ffprobe_path = os.path.join(base_directory, 'dependent', 'ffmpeg', 'bin', 'ffprobe.exe')
    else:
        ffprobe_path = shutil.which("ffprobe")
    if ffprobe_path and os.path.exists(ffprobe_path):
        printOnce("dep:ffprobe:ok", f"[INFO] FFprobe가 '{ffprobe_path}' 경로에 있습니다.")
        return ffprobe_path
    else:
        printOnce("dep:ffprobe:err", "[ERROR] FFprobe를 찾을 수 없습니다. 설치 후 PATH가 올바른지 확인해 주세요.")
        sys.exit(1)


# streamlink 경로를 가져오는 함수
def getStreamlink():
    if os.name == 'nt':
        streamlink_path = os.path.join(base_directory, 'dependent', 'streamlink', 'bin', 'streamlink.exe')
    else:
        streamlink_path = shutil.which("streamlink")
    if streamlink_path and os.path.exists(streamlink_path):
        printOnce("dep:streamlink:ok", f"[INFO] Streamlink가 '{streamlink_path}' 경로에 있습니다.")
        return streamlink_path
    else:
        printOnce("dep:streamlink:err", "[ERROR] Streamlink를 찾을 수 없습니다. 설치 후 PATH가 올바른지 확인해 주세요.")
        sys.exit(1)


# yt-dlp 경로를 가져오는 함수
def getYtDlp():
    if os.name == 'nt':
        yt_dlp_path = os.path.join(base_directory, 'dependent', 'yt-dlp', 'yt-dlp.exe')
    else:
        yt_dlp_path = shutil.which("yt-dlp")
    if yt_dlp_path and os.path.exists(yt_dlp_path):
        logger.info(f"yt-dlp가 '{yt_dlp_path}' 경로에 있습니다.")
        return yt_dlp_path
    else:
        logger.error(f"yt-dlp를 찾을 수 없습니다. 설치 후 PATH가 올바른지 확인해 주세요.")
        sys.exit(1)


# Aria2c 경로를 가져오는 함수
def getAria2c():
    if os.name == 'nt':
        aria2c_path = os.path.join(base_directory, 'dependent', 'aria2c', 'aria2c.exe')
    else:
        aria2c_path = shutil.which("aria2c")
    if aria2c_path and os.path.exists(aria2c_path):
        logger.info(f"Aria2c가 '{aria2c_path}' 경로에 있습니다.")
        return aria2c_path
    else:
        logger.error(f"Aria2c를 찾을 수 없습니다. 설치 후 PATH가 올바른지 확인해 주세요.")
        sys.exit(1)


# ytarchive 경로를 가져오는 함수
def getYtarchive():
    if os.name == 'nt':
        ytarchive_path = os.path.join(base_directory, 'dependent', 'ytarchive', 'ytarchive.exe')
    else:
        ytarchive_path = shutil.which("ytarchive")

    if ytarchive_path and os.path.exists(ytarchive_path):
        printOnce("dep:ytarchive:ok", f"[INFO] ytarchive가 '{ytarchive_path}' 경로에 있습니다.")
        return ytarchive_path
    else:
        printOnce("dep:ytarchive:err", "[ERROR] ytarchive를 찾을 수 없습니다. 설치 후 PATH가 올바른지 확인해 주세요.")
        sys.exit(1)