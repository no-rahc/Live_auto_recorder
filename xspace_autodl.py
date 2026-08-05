# -*- coding: utf-8 -*-

import os
import sys
import json
import re
import asyncio
import random
import locale
import shutil
import subprocess
from datetime import datetime, timedelta
from typing import Dict, List, Any

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
JSON_DIR    = os.path.join(BASE_DIR, "json")
CONFIG_PATH = os.path.join(JSON_DIR, "xchannels.json")
COOKIE_PATH = os.path.join(JSON_DIR, "xcookie.txt")

FFMPEG_PATH = os.path.join(BASE_DIR, "dependent", "ffmpeg", "bin", "ffmpeg.exe")

DEFAULT_OUTPUT_DIR      = os.path.join(BASE_DIR, "xspaces")
DEFAULT_RECHECK_SEC     = 120
DEFAULT_LOG_DIR         = os.path.join(BASE_DIR, "log")
DEFAULT_LOG_RETENTION   = 3
DEFAULT_MAX_LOG_FILES   = 500

FILENAME_FMT = r"[%(creator_screen_name)s] %(title)s - %(start_date)s (%(id)s).m4a"

AUTH_ERR_PAT = re.compile(r"(401|403|csrf|cookie|auth|unauthoriz|forbidden|guest)", re.I)
NOT_LIVE_PAT = re.compile(r"(Broadcast ID is not available|User is probably not live)", re.I)
URL_ERR_PAT  = re.compile(r"Invalid Twitter user URL", re.I)

TIME_PAT = re.compile(r"time=(\d{2}:\d{2}:\d{2}(?:\.\d{1,2})?)", re.I)
SIZE_PAT = re.compile(r"size=\s*([0-9]+)\s*k[iI]B", re.I)

default_encoding = locale.getpreferredencoding()

_cookie_mtime = None
_cookie_ok    = None

APP_NAME    = "xspace_autodl"
APP_VERSION = "0.1.0"


def printBanner():
    print(f"{APP_NAME} v{APP_VERSION}")


def _fmt_mib(kib):
    try:
        if kib is None:
            return ""
        return f"(약 {kib/1024:.1f} MiB)"
    except Exception:
        return ""


async def streamLines(reader, chunk_size: int = 8192):
    buf = b""
    while True:
        chunk = await reader.read(chunk_size)
        if not chunk:
            if buf:
                yield buf
            break
        buf += chunk
        buf = buf.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        while True:
            nl = buf.find(b"\n")
            if nl == -1:
                if len(buf) > 65536:
                    yield buf
                    buf = b""
                break
            line, buf = buf[:nl], buf[nl+1:]
            yield line



def ensureDependencies() -> None:
    try:
        __import__("twspace_dl")
        print("[INFO] twspace-dl: OK")
    except ImportError:
        print("[INFO] twspace-dl 미설치 → 자동 설치 시도")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "twspace-dl"], check=True)
            __import__("twspace_dl")
            print("[INFO] twspace-dl 설치 완료")
        except Exception as e:
            print(f"[WARN] twspace-dl 설치 실패: {e} (계속 진행)")

def ensureFfmpeg(ffmpeg_path: str = FFMPEG_PATH) -> None:
    if shutil.which("ffmpeg"):
        print("[INFO] ffmpeg: PATH 에서 감지됨")
        return
    if ffmpeg_path and os.path.isfile(ffmpeg_path):
        try:
            subprocess.run([ffmpeg_path, "-version"], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, check=True)
            ffdir = os.path.dirname(ffmpeg_path)
            os.environ["PATH"] = ffdir + os.pathsep + os.environ.get("PATH", "")
            print(f"[INFO] ffmpeg: explicit 경로 사용 → {ffmpeg_path}")
            return
        except Exception as e:
            print(f"[WARN] 지정 ffmpeg 테스트 실패: {e}")
    print("[WARN] ffmpeg 미감지. PATH 추가 또는 dependent\\ffmpeg\\bin\\ffmpeg.exe 확인 필요 (계속 진행)")

def _normUser(u: str) -> str:
    return (u or "").strip().lstrip("@")

def _parseCookieTokens(cookie_path: str) -> dict:
    tokens = {}
    try:
        with open(cookie_path, "r", encoding="utf-8", errors="ignore") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                if line.startswith("#HttpOnly_"):
                    line = line[len("#HttpOnly_"):]
                elif line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 7:
                    domain, name, value = parts[0], parts[5], parts[6]
                    domain = domain.lstrip(".").lower()
                    if domain.endswith("twitter.com") or domain.endswith("x.com"):
                        tokens[name] = value
    except Exception:
        pass
    return tokens

def ensureCookieFile() -> None:
    if os.path.isfile(COOKIE_PATH):
        return
    os.makedirs(JSON_DIR, exist_ok=True)
    try:
        with open(COOKIE_PATH, "w", encoding="utf-8") as f:
            f.write("# Netscape HTTP Cookie File\n# 여기에 X(Twitter) 브라우저 쿠키를 붙여넣으세요. (x.com/twitter.com)\n")
        print(f"[INFO] 쿠키 파일 생성: {COOKIE_PATH}")
        print("[GUIDE] 브라우저에서 x.com 쿠키를 내보내어 json\\xcookie.txt 에 저장한 뒤 다시 실행해주세요.")
    except Exception as e:
        print(f"[WARN] 쿠키 파일 자동 생성 실패: {e}")

def isCookieValid() -> bool:
    tokens = _parseCookieTokens(COOKIE_PATH)
    ok = bool(tokens.get("auth_token")) and bool(tokens.get("ct0"))
    if ok:
        print("[INFO] 쿠키 검증: OK(auth_token/ct0 발견)")
    else:
        print("[WARN] 쿠키 검증 실패: auth_token/ct0 누락. json\\xcookie.txt 내용을 확인하세요.")
    return ok


def checkCookieIfChanged() -> bool:
    global _cookie_mtime, _cookie_ok
    try:
        mt = os.path.getmtime(COOKIE_PATH)
    except FileNotFoundError:
        ensureCookieFile()
        return False
    if _cookie_mtime != mt:
        _cookie_ok = isCookieValid()
        _cookie_mtime = mt
    return bool(_cookie_ok)


def loadConfig() -> Dict[str, Any]:
    if not os.path.exists(JSON_DIR):
        os.makedirs(JSON_DIR, exist_ok=True)

    if not os.path.isfile(CONFIG_PATH):
        print("[WARN] json/xchannels.json 없음 → 기본 파일 생성")
        sample = {
            "users": ["@user1", "@user2"],
            "recheckInterval": DEFAULT_RECHECK_SEC,
            "output_dir": "./xspaces",
            "log_dir": "./log",
            "log_retention_days": DEFAULT_LOG_RETENTION,
            "max_log_files": DEFAULT_MAX_LOG_FILES
        }
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(sample, f, ensure_ascii=False, indent=2)

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f) or {}

    users: List[str] = [_normUser(u) for u in (raw.get("users") or []) if str(u).strip()]
    if not users:
        print("[ERROR] xchannels.json: 'users' 가 비어있습니다.")
        raise SystemExit(1)

    recheck_sec = raw.get("recheckInterval", raw.get("poll_seconds", DEFAULT_RECHECK_SEC))
    try:
        recheck_sec = int(recheck_sec)
    except Exception:
        recheck_sec = DEFAULT_RECHECK_SEC
    if recheck_sec < 15:
        print("[WARN] recheckInterval 이 너무 낮음(권장 ≥30). 30초로 보정")
        recheck_sec = 30

    output_dir = raw.get("output_dir", raw.get("output_root", "./xspaces"))
    output_abs = os.path.abspath(output_dir) if os.path.isabs(output_dir) else os.path.abspath(os.path.join(BASE_DIR, output_dir))
    os.makedirs(output_abs, exist_ok=True)

    log_dir = raw.get("log_dir", "./log")
    log_abs = os.path.abspath(log_dir) if os.path.isabs(log_dir) else os.path.abspath(os.path.join(BASE_DIR, log_dir))
    os.makedirs(log_abs, exist_ok=True)
    log_retention_days = int(raw.get("log_retention_days", DEFAULT_LOG_RETENTION))
    max_log_files = int(raw.get("max_log_files", DEFAULT_MAX_LOG_FILES))

    ensureCookieFile()
    cookie_ok = os.path.isfile(COOKIE_PATH) and isCookieValid()

    # 최초 검증 이후 mtime 기억하여 첫 루프에서 중복 검증 방지
    global _cookie_mtime, _cookie_ok
    try:
        _cookie_mtime = os.path.getmtime(COOKIE_PATH)
    except FileNotFoundError:
        _cookie_mtime = None
    _cookie_ok = cookie_ok

    return {
        "users": users,
        "recheck_sec": recheck_sec,
        "output_abs": output_abs,
        "cookie_path": COOKIE_PATH,
        "cookie_ok": cookie_ok,
        "log_dir": log_abs,
        "log_retention_days": log_retention_days,
        "max_log_files": max_log_files
    }


def cleanupLogs(log_dir: str, retention_days: int = DEFAULT_LOG_RETENTION, max_files: int = DEFAULT_MAX_LOG_FILES) -> None:
    try:
        files = [os.path.join(log_dir, f) for f in os.listdir(log_dir)
                 if f.startswith(".twspace-dl.") and os.path.isfile(os.path.join(log_dir, f))]
        cutoff = datetime.now() - timedelta(days=retention_days)
        for p in files:
            try:
                if datetime.fromtimestamp(os.path.getmtime(p)) < cutoff:
                    os.remove(p)
            except Exception:
                pass
        files = [os.path.join(log_dir, f) for f in os.listdir(log_dir)
                 if f.startswith(".twspace-dl.") and os.path.isfile(os.path.join(log_dir, f))]
        if len(files) > max_files:
            files.sort(key=lambda p: os.path.getmtime(p))
            for p in files[:len(files) - max_files]:
                try:
                    os.remove(p)
                except Exception:
                    pass
    except Exception:
        pass


def buildCmd(user: str, cfg: Dict[str, Any]) -> List[str]:
    user_dir = os.path.join(cfg["output_abs"], user)
    os.makedirs(user_dir, exist_ok=True)
    return [
        sys.executable, "-m", "twspace_dl",
        "-U", f"https://twitter.com/{user}",
        "-c", cfg["cookie_path"],
        "-o", os.path.join(user_dir, FILENAME_FMT),
        "-l"
    ]


async def monitorUser(user: str, cfg: Dict[str, Any]) -> None:
    base_sleep = int(cfg["recheck_sec"])
    bad_cookie_backoff = max(base_sleep * 10, 300)

    while True:
        # 쿠키 점검 (파일 변경 시에만 실제 검사)
        if not checkCookieIfChanged():
            print(f"[안내] '{user}' 유저 감시를 일시 대기합니다. 쿠키가 유효하지 않습니다. {base_sleep}초 후 다시 확인합니다.")
            await asyncio.sleep(base_sleep)
            continue

        print(f"[{datetime.now():%F %T}] start @{user}")
        try:
            proc = await asyncio.create_subprocess_exec(
                *buildCmd(user, cfg),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=cfg["log_dir"]
            )
        except Exception as e:
            print(f"[WARN] 프로세스 시작 실패(@{user}): {e} → {base_sleep}초 후 재시도")
            await asyncio.sleep(base_sleep)
            continue


        saw_auth_error = False
        saw_not_live  = False
        saw_url_error = False

        is_recording = False
        last_progress_print = 0
        cur_time_text = ""
        cur_size_kib  = None

        try:
            async for raw in streamLines(proc.stdout):
                line = raw.decode(default_encoding, errors="replace").rstrip()
                print(f"[{user}] {line}")

                if AUTH_ERR_PAT.search(line):
                    saw_auth_error = True
                if NOT_LIVE_PAT.search(line):
                    saw_not_live = True
                if URL_ERR_PAT.search(line):
                    saw_url_error = True

                m_t = TIME_PAT.search(line)
                m_s = SIZE_PAT.search(line)
                if m_t:
                    cur_time_text = m_t.group(1)
                    if not is_recording:
                        is_recording = True
                        print(f"[알림] '{user}' 스페이스 녹음 시작을 감지했습니다.")
                if m_s:
                    try:
                        cur_size_kib = int(m_s.group(1))
                    except Exception:
                        pass

                if is_recording:
                    now_ts = datetime.now().timestamp()
                    if now_ts - last_progress_print >= 10:  # 10초마다 한 줄
                        size_hint = _fmt_mib(cur_size_kib)
                        if cur_time_text or size_hint:
                            print(f"[녹음중] '{user}' {cur_time_text} {size_hint}".rstrip())
                            last_progress_print = now_ts

        except Exception as e:
            print(f"[WARN] 로그 스트림 처리 중 예외 발생: {e}")

        code = await proc.wait()

        cleanupLogs(cfg["log_dir"], cfg["log_retention_days"], cfg["max_log_files"])

        # 인증 에러가 감지되었으면 다음 루프에서 쿠키 즉시 재검사
        if saw_auth_error:
            global _cookie_mtime
            _cookie_mtime = None

        # 백오프 계산 
        if saw_url_error:
            sleep_s, reason = base_sleep, "url/format"
        elif saw_not_live:
            sleep_s, reason = base_sleep, "not-live"
        elif saw_auth_error:
            sleep_s, reason = bad_cookie_backoff, "auth/cookie?"
        elif code == 0:
            sleep_s, reason = base_sleep, "normal"
        else:
            sleep_s, reason = base_sleep, f"exit{code}"

        if reason == "not-live":
            print(f"[안내] '{user}' 유저의 스페이스가 탐색되지 않았습니다. {base_sleep}초 후 다시 탐색합니다.")

        sleep_s = int(sleep_s * random.uniform(0.85, 1.15))
        print(f"[{datetime.now():%F %T}] exit @{user} -> {code}; backoff={sleep_s}s ({reason})")
        await asyncio.sleep(sleep_s)


async def main() -> None:
    printBanner()  
    ensureDependencies()
    ensureFfmpeg()
    cfg = loadConfig()
    tasks = [asyncio.create_task(monitorUser(u, cfg)) for u in cfg["users"]]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[INFO] 사용자 중지 요청으로 종료합니다.")
