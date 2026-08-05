# -*- coding: utf-8 -*-

import os
import sys
import re
import shutil
import locale
import argparse
import subprocess

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
JSON_DIR   = os.path.join(BASE_DIR, "json")
COOKIE_PATH_DEFAULT = os.path.join(JSON_DIR, "xcookie.txt")
FFMPEG_PATH = os.path.join(BASE_DIR, "dependent", "ffmpeg", "bin", "ffmpeg.exe")
LOG_DIR    = os.path.join(BASE_DIR, "log")

OUT_FMT_REPLAY = r"[%(creator_screen_name)s] %(title)s (%(id)s).m4a"
ID_RE   = re.compile(r"[A-Za-z0-9_-]{6,}")
URL_RE  = re.compile(r"^https?://(x\.com|twitter\.com)/i/spaces/([A-Za-z0-9_-]{6,})/?$", re.I)
AUTH_ERR_PAT = re.compile(r"(401|403|csrf|cookie|auth|unauthoriz|forbidden|guest)", re.I)
default_encoding = locale.getpreferredencoding()

APP_NAME    = "xspace_replay"
APP_VERSION = "0.1.0"


def printBanner():
    print(f"{APP_NAME} v{APP_VERSION}")


def ensureDependencies():
    try:
        __import__("twspace_dl")
        print("[INFO] twspace-dl: OK")
    except ImportError:
        print("[INFO] twspace-dl 미설치 → 자동 설치")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "twspace-dl"], check=True)
            __import__("twspace_dl")
            print("[INFO] twspace-dl 설치 완료")
        except Exception as e:
            print(f"[WARN] twspace-dl 설치 실패: {e}")


def ensureFfmpeg():
    if shutil.which("ffmpeg"):
        print("[INFO] ffmpeg: PATH 감지")
        return
    if os.path.isfile(FFMPEG_PATH):
        os.environ["PATH"] = os.path.dirname(FFMPEG_PATH) + os.pathsep + os.environ.get("PATH", "")
        print(f"[INFO] ffmpeg: explicit 경로 사용 → {FFMPEG_PATH}")
        return
    print("[WARN] ffmpeg 미감지. dependent\\ffmpeg\\bin\\ffmpeg.exe 확인 권장")


def normalizeSpaceUrl(u: str) -> str:
    u = u.strip()
    if not u:
        return ""
    if not u.startswith("http"):
        if ID_RE.fullmatch(u):
            return f"https://twitter.com/i/spaces/{u}"
        return ""
    return u.replace("https://x.com", "https://twitter.com")


def extractSpaceId(u: str) -> str:
    m = URL_RE.match(u.replace("https://x.com", "https://twitter.com"))
    return m.group(2) if m else ""


def askOneLine(prompt: str) -> str:
    print(prompt, flush=True)
    return input("> ").strip()


def askUrlsInteractive() -> list[str]:
    while True:
        raw = askOneLine("다운로드할 스페이스 링크 또는 Space ID를 입력하세요. (여러 개면 공백/쉼표로 구분)")
        if not raw:
            print("[INFO] 입력이 비었습니다. 다시 입력하세요.")
            continue
        urls = [normalizeSpaceUrl(s) for s in raw.replace(",", " ").split()]
        urls = [u for u in urls if u and extractSpaceId(u)]
        if urls:
            return urls
        print("[WARN] 형식이 올바르지 않습니다. 예) https://twitter.com/i/spaces/1ABcdEFgHiJk 또는 ID만")


def askPathForSave(default_path: str) -> str:
    print(f"저장할 디렉토리 경로를 입력하세요. 예) D:/test\n엔터를 누르면 프로그램과 같은 경로에 저장됩니다. (기본: {default_path})", flush=True)
    p = input("> ").strip() or default_path
    if not os.path.isabs(p):
        p = os.path.abspath(os.path.join(BASE_DIR, p))
    return p


def ensureCookieFile() -> None:
    if os.path.isfile(COOKIE_PATH_DEFAULT):
        return
    os.makedirs(JSON_DIR, exist_ok=True)
    try:
        with open(COOKIE_PATH_DEFAULT, "w", encoding="utf-8") as f:
            f.write("# Netscape HTTP Cookie File\n# 여기에 X(Twitter) 브라우저 쿠키를 붙여넣으세요. (x.com/twitter.com)\n")
        print(f"[INFO] 쿠키 파일 생성: {COOKIE_PATH_DEFAULT}")
        print("[GUIDE] 브라우저에서 x.com 쿠키를 내보내어 json\\xcookie.txt 에 저장한 뒤 다시 실행해주세요.")
    except Exception as e:
        print(f"[WARN] 쿠키 파일 자동 생성 실패: {e}")


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


def checkCookieOnce() -> bool:
    ensureCookieFile()
    t = _parseCookieTokens(COOKIE_PATH_DEFAULT)
    ok = bool(t.get("auth_token")) and bool(t.get("ct0"))
    if ok:
        print("[INFO] 쿠키 검증: OK(auth_token/ct0 발견)")
    else:
        print("[WARN] 쿠키 검증 실패: auth_token/ct0 누락. json\\xcookie.txt 내용을 확인하세요. (진행은 계속됩니다)")
    return ok


def downloadOne(url: str, outdir: str, cookie_path: str) -> bool:
    url = normalizeSpaceUrl(url)
    sid = extractSpaceId(url)
    if not sid:
        print("[WARN] URL 형식이 올바르지 않습니다. 다시 입력하세요.")
        return False

    os.makedirs(outdir, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)

    outtmpl = os.path.join(outdir, OUT_FMT_REPLAY)
    cmd = [
        sys.executable, "-m", "twspace_dl",
        "-i", url,
        "-c", cookie_path,
        "-o", outtmpl,
        "-l"
    ]

    before = {f for f in os.listdir(outdir) if f.lower().endswith(".m4a")}

    print(f"[REPLAY] {url}")
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=LOG_DIR)
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            s = line.decode(default_encoding, errors="replace").rstrip()
            print(f"[twspace-dl] {s}")
        proc.wait()
    except Exception as e:
        print(f"[ERROR] {e}")
        return False

    after = {f for f in os.listdir(outdir) if f.lower().endswith(".m4a")}
    newly = list(after - before)
    if newly:
        print(f"[OK] 저장 완료 → {outdir}")
        return True

    target_exists = any(f.endswith(f"({sid}).m4a") for f in after)
    if target_exists:
        print(f"[OK] 저장 확인 → {outdir}")
        return True

    print("[WARN] 저장 결과를 확인하세요. (리플레이가 없거나 접근 차단/중단일 수 있음)")
    return False


def sessionLoop(initial_urls: list[str] | None, outdir: str, cookie_path: str):
    urls = initial_urls[:] if initial_urls else []
    while True:
        if not urls:
            urls = askUrlsInteractive()
        success = 0
        for u in urls:
            if downloadOne(u, outdir, cookie_path):
                success += 1
        print(f"[DONE] {success}/{len(urls)} 성공")
        ans = askOneLine("추가로 받을 링크가 있습니까? (y/N)").lower()
        if ans != "y":
            break
        urls = []


def main():
    ap = argparse.ArgumentParser(description="X 스페이스 리플레이 다운로더 - twspace-dl")
    ap.add_argument("urls", nargs="*", help="스페이스 URL 또는 Space ID")
    ap.add_argument("--dir", help="저장 디렉토리(엔터 시 프로그램 경로)")
    args = ap.parse_args()

    printBanner()
    ensureDependencies()
    ensureFfmpeg()
    checkCookieOnce()

    initial = [normalizeSpaceUrl(u) for u in (args.urls or [])]
    initial = [u for u in initial if u and extractSpaceId(u)]
    if not initial:
        initial = askUrlsInteractive()

    outdir = args.dir or askPathForSave(BASE_DIR)

    sessionLoop(initial, outdir, COOKIE_PATH_DEFAULT)

if __name__ == "__main__":
    main()
