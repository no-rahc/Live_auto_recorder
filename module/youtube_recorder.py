from module.log_setup import get_logger
logger = get_logger("youtube_recorder")
import os
import asyncio
import aiohttp
import json
import re
import shlex
import time
import unicodedata
import subprocess
import shutil
import contextlib
import psutil
import glob
import signal
import errno
import sys
import hashlib
import math

if os.name == 'nt':
    import ctypes

from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
from typing import Optional, Awaitable, Callable
from pathlib import Path

from module.data_manager import (
    RecorderManager, uniqueFilename, moveDirectory, sendTelegram, last_notified_state,
    base_directory, getFFmpeg, getYtarchive, loadConfig, ysaveCookies, toBool
)

from module.loop_watchdog import (
    spawnHeartbeat, cancelTaskSafely
)

# RecorderManager 클래스 인스턴스 생성
recorder_manager = RecorderManager()

# ytarchive 임시작업 루트
TMP_ROOT = os.path.join(base_directory, "tmp", "ytarchive")
os.makedirs(TMP_ROOT, exist_ok=True)

# 재탐색 지터 전역
START_MONO = time.monotonic()
JITTER_RATIO = float(os.environ.get("RECHECK_JITTER_RATIO", "0.15"))
_JITTER_PHASE = {}  # {channel_id: phase(sec)}


# 유니코드 정규화 후 ASCII로 변환 (불필요한 문자는 제거)
def sanitize_filename(s: str) -> str:
    normalized = unicodedata.normalize('NFKC', s)
    return re.sub(r'[\\/:*?"<>|\+\[\]【】「」『』]', '_', normalized)


# heartbeat용 유튜브 프로브(라이브 유지 확인) 
def _make_youtube_probe(channel, ycookie_path=None):
    async def _probe():
        try:
            md = await getYoutubeMetadata(channel, ycookie_path)
            return bool(md.get("is_live"))
        except Exception:
            return False
    return _probe


# 유튜브 쿠키 검증 함수
def validateCookies(cookie_path: str | None, *, include_header: bool = False):
    try:
        if not cookie_path or not os.path.exists(cookie_path):
            return (False, '쿠키 파일이 존재하지 않습니다.') if not include_header else (False, '쿠키 파일이 존재하지 않습니다.', None)

        required_cookies = ['SAPISID', '__Secure-3PSID', '__Secure-3PAPISID']

        with open(cookie_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        parsed = {}
        cookie_pairs = []  # header 만들 때 사용
        names_to_take = {
            'SAPISID','__Secure-3PSID','__Secure-3PAPISID',
            'HSID','SSID','APISID','SID','SIDCC','PAPISID',
            'CONSENT','YSC','VISITOR_INFO1_LIVE'
        }

        for line in lines:
            if not line.strip() or line.startswith('#'):
                continue
            # Netscape: domain, flag, path, secure, expires, name, value
            parts = line.strip().split('\t')
            if len(parts) >= 7:
                domain, _, _, _, _, name, value = parts[:7]
                parsed[name] = value
                if ('youtube.com' in domain or 'google.com' in domain) and (name in names_to_take or name.startswith('__Secure-')):
                    cookie_pairs.append(f"{name}={value}")

        missing = [k for k in required_cookies if k not in parsed]
        ok = not missing
        msg = '쿠키가 올바르게 설정되었습니다.' if ok else f"다음 쿠키들이 누락되었습니다: {', '.join(missing)}"

        if include_header:
            header = "; ".join(cookie_pairs) if cookie_pairs else None
            return ok, msg, header
        else:
            return ok, msg

    except Exception as e:
        logger.info(f"쿠키 검증 중 오류 발생: {e}")
        return (False, '쿠키 검증 중 오류 발생') if not include_header else (False, '쿠키 검증 중 오류 발생', None)


#  SIGINT / CTRL-C 전송 함수
def sendInterrupt(proc: subprocess.Popen):
    if os.name == 'nt':
        try:
            # 현재 프로세스는 Ctrl 시그널 무시
            try:
                ctypes.windll.kernel32.SetConsoleCtrlHandler(None, True)
            except Exception:
                pass
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        except ValueError:
            ctypes.windll.kernel32.GenerateConsoleCtrlEvent(1, proc.pid)
        finally:
            # 다시 원복
            try:
                ctypes.windll.kernel32.SetConsoleCtrlHandler(None, False)
            except Exception:
                pass
    else:
        os.killpg(os.getpgid(proc.pid), signal.SIGINT)


# 품질별 프레임 추출 함수
def extractFps(data):
    fps_values = []
    streaming_data = data.get("streamingData", {})
    adaptive_formats = streaming_data.get("adaptiveFormats", [])
    for fmt in adaptive_formats:
        fps = fmt.get("fps")
        if fps:
            fps_values.append(fps)
    if fps_values:
        return max(fps_values)
    return None


# 최대 해상도 높이(px) 추출
def extractResolution(data):
    heights = []
    streaming_data = data.get("streamingData", {})
    adaptive_formats = streaming_data.get("adaptiveFormats", [])
    for fmt in adaptive_formats:
        if "video/" in (fmt.get("mimeType") or ""):
            h = fmt.get("height")
            if isinstance(h, int):
                heights.append(h)
            else:
                # qualityLabel: "1080p60" 등인 경우 파싱
                ql = fmt.get("qualityLabel") or ""
                m = re.match(r"^(\d+)p", ql)
                if m and m.group(1).isdigit():
                    heights.append(int(m.group(1)))
    return max(heights) if heights else None



# 기본 메타데이터 반환 함수
def default_metadata():
    return {
        'is_live': False,
        'video_id': None,
        'channel_name': 'Unknown Channel',
        'live_title': '정보 없음',
        'thumbnail_url': '/static/img/youtube_thumbnail.png', 
        'category': '카테고리 없음',
        'record_quality': 'best',
        'resolution': 'Unknown', 
        'frame_rate': 'Unknown', 
        'adult': False,
        'start_time': None, 
        'dash_manifest_url': None, 
    }


# 유튜브 라이브 메타데이터 가져오기
async def getYoutubeMetadata(channel, ycookie_path=None):
    def _default_meta():
        try:
            d = default_metadata()
        except Exception:
            d = {
                "platform": "youtube",
                "id": channel.get("id", "unknown"),
                "is_live": False,
                "live_title": "정보 없음",
                "category": "정보 없음",
                "thumbnail_url": "/static/img/youtube_thumbnail.png",
                "watch_url": None,
                "video_id": None,
                "scheduled_start_time_dt": None,
            }
        # 보강 필드
        d.setdefault("is_live_now", False)
        return d

    try:
        platform = "youtube"
        cid = channel.get("id", "").strip() or "unknown"

        # 1) 채널 LIVE URL (핸들/채널ID 모두 대응)
        ident = cid
        if ident.startswith("UC"):
            live_url = f"https://www.youtube.com/channel/{ident}/live"
        elif ident.startswith("@"):
            live_url = f"https://www.youtube.com/{ident}/live"
        else:
            live_url = f"https://www.youtube.com/@{ident}/live"

        # 2) 쿠키 준비
        ok_cookie, _, cookie_header = (
            validateCookies(ycookie_path, include_header=True) if ycookie_path
            else (False, "", None)
        )

        async def _fetch(url: str, with_cookie: bool):
            client_timeout = aiohttp.ClientTimeout(total=10.0, connect=5.0)
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            }
            if with_cookie and cookie_header:
                headers["Cookie"] = cookie_header

            async with aiohttp.ClientSession(timeout=client_timeout) as session:
                async with session.get(url, headers=headers, allow_redirects=True) as resp:
                    html = await resp.text()
                    final_url = str(resp.url)
                    return html, final_url

        # (a) 쿠키 → (b) 비쿠키
        html, final_url = None, None
        if ok_cookie and cookie_header:
            try:
                html, final_url = await _fetch(live_url, True)
            except asyncio.TimeoutError:
                html, final_url = None, None
        if html is None:
            try:
                html, final_url = await _fetch(live_url, False)
            except asyncio.TimeoutError:
                html, final_url = None, None

        if not html:
            return _default_meta()

        # 3) player JSON 추출
        def _extract_player_json(page_html: str):
            patterns = [
                r'ytInitialPlayerResponse\s*=\s*({.*?});',
                r'"ytInitialPlayerResponse"\s*:\s*({.*?})\s*,\s*"(?:ytInitialData|INNERTUBE)',
            ]
            for pat in patterns:
                m = re.search(pat, page_html, re.S)
                if m:
                    try:
                        return json.loads(m.group(1))
                    except Exception:
                        continue
            return None

        player = _extract_player_json(html)

        # 4) videoId 탐색
        video_id = None
        if isinstance(player, dict):
            video_id = ((player.get("videoDetails") or {}).get("videoId")) or None
        if not video_id:
            mv = re.search(r'"videoId"\s*:\s*"([A-Za-z0-9_-]{11})"', html)
            if mv:
                video_id = mv.group(1)
        if not video_id and final_url and "/watch" in final_url:

            try:
                qs = parse_qs(urlparse(final_url).query)
                video_id = (qs.get("v") or [None])[0]
            except Exception:
                pass

        # 5) 메타 필드 채우기
        is_live = False
        is_live_now = False
        live_title = "정보 없음"
        category = "정보 없음"
        scheduled_dt = None
        watch_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else None
        thumb = (f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id
                 else "/static/img/youtube_thumbnail.png")

        if isinstance(player, dict):
            vd = player.get("videoDetails") or {}
            micro = (player.get("microformat") or {}).get("playerMicroformatRenderer") or {}
            lb = micro.get("liveBroadcastDetails") or {}
            ps = (player.get("playabilityStatus") or {})
            status_val = (ps.get("status") or "").upper()

            # 제목/카테고리
            live_title = (vd.get("title")
                          or (micro.get("title") or {}).get("simpleText")
                          or "정보 없음")
            category = (micro.get("category") or vd.get("category") or "정보 없음")

            # 라이브 판정(엄격)
            is_live_now = bool(lb.get("isLiveNow"))
            if status_val == "LIVE_STREAM_OFFLINE":
                is_live_now = False

            # 보수적으로: live_now가 최우선. OK+liveStreamability는 보조 신호.
            is_live = bool(is_live_now or (status_val == "OK" and ps.get("liveStreamability")))

            # 예정/시작 시간
            ts = lb.get("startTimestamp") or lb.get("scheduledStartTime")
            if ts:
                try:
                    if isinstance(ts, str) and ts.endswith("Z"):
                        ts = ts[:-1] + "+00:00"
                    scheduled_dt = datetime.fromisoformat(ts) if isinstance(ts, str) else None
                except Exception:
                    scheduled_dt = None

        # 6) 최종 리턴
        fps_val = None
        res_val = None

        try:
            if isinstance(player, dict):
                fps_val = extractFps(player)
                res_val = extractResolution(player)
        except Exception:
            pass

        return {
            "platform": platform,
            "id": cid,
            "is_live": bool(is_live),
            "is_live_now": bool(is_live_now),
            "live_title": live_title or "정보 없음",
            "category": category or "정보 없음",
            "thumbnail_url": thumb or "/static/img/youtube_thumbnail.png",
            "watch_url": watch_url,
            "video_id": video_id,
            "scheduled_start_time_dt": scheduled_dt,
            "frame_rate": (int(fps_val) if isinstance(fps_val, int) else None),
            "resolution": (int(res_val) if isinstance(res_val, int) else None),
        }

    except Exception as e:
        logger.error(f"getYoutubeMetadata exception: {e}")
        return _default_meta()


# 유튜브 녹화 명령 생성 함수
def buildCommand(channel, output_dir, quality, extension, metadata,
                 cookies_valid, filenamePattern=None, ycookie_path=None):
    try:
        if channel is None or metadata is None:
            logger.error("채널 또는 메타데이터가 없습니다.")
            return None, None, None

        # 출력 경로
        if not os.path.isabs(output_dir):
            output_dir = os.path.join(base_directory, output_dir)
        os.makedirs(output_dir, exist_ok=True)

        # 메타 요약
        is_live      = bool(metadata.get("is_live"))
        is_live_now  = bool(metadata.get("is_live_now"))
        video_id     = metadata.get("video_id")
        handle       = (channel.get("id") or "").strip()

        # 파일명 패턴
        filenamePattern = filenamePattern or (
            "[{start_time}] {channel_name} {safe_live_title} {record_quality}{frame_rate}{file_extension}"
        )

        # 1) 날짜/시간 토큰 
        recording_time = datetime.now().strftime("%y%m%d_%H%M%S") 

        start_time_dt = None
        st_meta = metadata.get('start_time') or metadata.get('scheduled_start_time_dt')

        if isinstance(st_meta, datetime):
            start_time_dt = st_meta
        elif isinstance(st_meta, str):
            try:
                s = st_meta.replace('Z', '+00:00')
                start_time_dt = datetime.fromisoformat(s)
            except Exception:
                start_time_dt = None

        if not start_time_dt:
            start_time_dt = datetime.now()

        start_time = start_time_dt.strftime("%Y-%m-%d")  

        # 2) 채널/제목 정리
        channel_name = sanitize_filename(channel.get('name', 'Unknown Channel'))[:50]
        live_title = (metadata.get('live_title') or '녹화')

        # 개행/탭 → 공백, 앞뒤 공백 정리
        live_title = re.sub(r'[\r\n\t]+', ' ', live_title).strip()

        # 금지문자만 '공백'으로 치환 (언더바 쓰지 않음)
        safe_live_title = re.sub(r'[\\/*?:"<>|+]', ' ', live_title)

        # 다중 공백을 1칸으로 축약
        safe_live_title = re.sub(r'\s{2,}', ' ', safe_live_title).strip()

        # .format 충돌 방지용 중괄호 이스케이프 + 길이 제한
        safe_live_title = safe_live_title.replace('{', '{{').replace('}', '}}')[:55]


        # 3) 품질/프레임  (요청값 우선 → 파일명 오표기 방지)
        requested_q = (str(quality) or "best").lower()

        # 1) 기본: 요청 품질을 파일명에 반영
        m_req = re.match(r"^(\d+)p(?:60)?$", requested_q)
        if m_req:
            record_quality = f"{m_req.group(1)}p"
        else:
            record_quality = "best"  # best인 경우만 메타 보정 적용

        name_fps = 60 if requested_q.endswith("60") else 30

        # 2) 요청이 'best'일 때만 메타(실측)로 보정
        meta_fps = None
        try:
            mf = metadata.get("frame_rate")
            if mf not in (None, "Unknown", ""):
                meta_fps = int(mf)
        except Exception:
            meta_fps = None

        meta_res = 0
        try:
            mr = metadata.get("resolution")
            if mr not in (None, "Unknown", ""):
                meta_res = int(mr)
        except Exception:
            meta_res = 0

        if requested_q == "best":
            if meta_res > 0:
                record_quality = f"{meta_res}p"
            if meta_fps is not None:
                name_fps = 60 if meta_fps >= 59 else 30

        frame_rate_for_name = str(name_fps)


        # 3-1) 확장자 보강
        if requested_q == "best" and str(extension).lower() == ".mp4":
            try:
                res_hint = int(metadata.get("resolution") or 0)
            except Exception:
                res_hint = 0
            if res_hint > 1080:
                extension = ".mkv"


        # 4) 최종 파일명/경로
        final_filename = filenamePattern.format(
            start_time=start_time,
            recording_time=recording_time,
            channel_name=channel_name,
            safe_live_title=safe_live_title,
            record_quality=record_quality,
            frame_rate=frame_rate_for_name,
            file_extension=extension
        )
        output_final_path = os.path.join(output_dir, final_filename)
        prefix_path = os.path.splitext(output_final_path)[0]

        # 5) ytarchive 명령 구성
        ytarchive_cmd = [
            getYtarchive(),
            "--merge",
            "--threads", "3",
            "--temporary-dir", TMP_ROOT,   
        ]

        if extension.lower() == ".mkv":
            ytarchive_cmd.append("--mkv")

        # 쿠키: 유효성 판단과 무관하게 파일이 존재하면 전달 (CONSENT 최소 쿠키도 헤더 주입을 위해 필요)
        if ycookie_path and os.path.isfile(ycookie_path):
            ytarchive_cmd += ["--cookies", ycookie_path]

        # 대기/재시도 옵션 구성
        wait_args = []
        if video_id and is_live_now:
            # 지금 방송 중 → watch URL, 굳이 대기 플래그 필요 없음
            base_url = f"https://www.youtube.com/watch?v={video_id}"
            # 선택: 안정성 위해 재시도 간격만 넣어도 무해
            wait_args = ["-retry-stream", "15"]

        elif video_id:
            # 예정/대기 영상 → watch URL + '대기'
            base_url = f"https://www.youtube.com/watch?v={video_id}"
            wait_args = ["-w", "-retry-stream", "15"]
        else:
            # /live 감시
            if handle.startswith("UC"):
                base_url = f"https://www.youtube.com/channel/{handle}/live"
            elif handle.startswith("@"):
                base_url = f"https://www.youtube.com/{handle}/live"
            else:
                base_url = f"https://www.youtube.com/@{handle}/live" if handle else None
            if not base_url:
                logger.error("채널 핸들이 없어 --monitor-channel 폴백을 사용할 수 없습니다.")
                return None, None, None
            ytarchive_cmd.append("--monitor-channel")
            wait_args = ["-retry-stream", "15"]

        logger.debug(f"생성된 base_url: {base_url}")
        logger.debug(f"최종 파일명: {final_filename}")
        logger.debug(f"출력 파일 경로: {output_final_path}")

        # 옵션은 위치 인자 앞에
        ytarchive_cmd += wait_args
        ytarchive_cmd += ["-o", prefix_path, base_url, str(quality)]
        return ytarchive_cmd, prefix_path, output_final_path

    except Exception as e:
        logger.error(f"buildCommand 실행 중 오류: {e}")
        return None, None, None


# stdout 등 디버그 신호 읽기
async def readPipe(stream, channel_id: str, ch_name: str, final_q: Optional[asyncio.Queue] = None, cwd: Optional[str] = None,
                   expected_out: Optional[str] = None, on_final: Optional[Callable[[str], Awaitable[None]]] = None,):

    # 1) 병합 시작 신호: Download Finished / Muxing final file / Muxing to
    merge_start_pat = re.compile(r"(?:Download Finished|Muxing final file|Muxing to)\b", re.I)
    # 2) 병합 완료 신호: 최종 파일 경로 동반
    merge_done_pat  = re.compile(
        r"(?:Final file|Merged file is|Output file|Muxed to)\s*:?\s+(.+\.(?:mp4|mkv|ts))",
        re.I)

    buffer = ""
    while True:
        data = await stream.read(2048)
        if not data:
            break
        chunk = data.decode(errors='replace')
        logger.info(f"[{ch_name}] {chunk}", end='')

        buffer += chunk
        *lines, buffer = buffer.splitlines(True)
        for ln in lines:
            line = ln.rstrip("\r\n")

            # A) 병합 시작 신호 감지 → 녹화 종료/병합 시작 텔레그램
            if merge_start_pat.search(line):
                try:
                    if last_notified_state.get(channel_id) not in ("녹화종료", "병합완료"):
                        dur = recorder_manager.get_recording_duration(channel_id)  # "HH:MM:SS"
                        fname = os.path.basename(expected_out) if expected_out else None
                        msg = (
                            f"<b>{ch_name}</b> 녹화가 <b>종료</b>되었습니다. 병합을 시작합니다."
                            + (f" (녹화시간 {dur})" if dur else "")
                            + (f"\n<code>{fname}</code>" if fname else "")
                        )
                        sendTelegram(msg)
                        last_notified_state[channel_id] = "녹화종료"
                except Exception as _e:
                    logger.warning(f"merge-start telegram failed: {_e}")

            # B) 병합 완료 신호 감지 → 최종 파일 경로 처리
            m2 = merge_done_pat.search(line)
            if m2:
                p = m2.group(1).strip().strip("'\"")
                path = p if os.path.isabs(p) else os.path.join(cwd or "", p)
                if final_q:
                    await final_q.put(path)
                if on_final:
                    asyncio.create_task(on_final(path))

    # 종료 시 잔여 버퍼에서 완료 한 번 더 체크
    if buffer:
        m2 = merge_done_pat.search(buffer)
        if m2:
            p = m2.group(1).strip().strip("'\"")
            path = p if os.path.isabs(p) else os.path.join(cwd or "", p)
            if final_q:
                await final_q.put(path)
            if on_final:
                asyncio.create_task(on_final(path))


# ytarchive 병합 확장자 추정
def extFromQuality(q: str) -> str:
    try:
        m = re.search(r'(\d{3,4})p', str(q).lower())
        if m:
            level = int(m.group(1))
            return ".mkv" if level > 1080 else ".mp4"
    except Exception:
        pass
    return ".mp4"


# 프로세스 트리를 종료하는 함수
def killProcessTree(pid):
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        for child in children:
            logger.debug(f"종료 중인 하위 프로세스 PID: {child.pid}")
            child.kill()
        parent.kill()
        logger.debug(f"프로세스 트리가 종료되었습니다. PID: {pid}")
    except psutil.NoSuchProcess:
        logger.warning(f"프로세스를 찾을 수 없습니다. PID: {pid}")


# ytarchive 임시 파일/폴더 삭제 함수 
def cleanupTmp(prefix_path: str, video_id: str | None = None, retries: int = 12, delay: float = 0.6):
    base_dir = os.path.dirname(prefix_path)
    stem     = os.path.basename(prefix_path)

    def _win_long(p: str) -> str:
        if os.name == 'nt' and not p.startswith('\\\\?\\') and re.match(r'^[A-Za-z]:\\', p):
            return '\\\\?\\' + p
        return p

    # 출력 폴더: 프리픽스 기반 잔여물 수집 (변종까지 startswith로 포괄)
    def _collect_outputs():
        targets = []
        try:
            for entry in os.scandir(base_dir):
                name = entry.name
                full = os.path.join(base_dir, name)
                if (
                    name.startswith(stem + ".f")            # .f135, .f140, .f*.ts, .f*.m4a 등 전부
                    or name.startswith(stem + ".ffmpeg")    # .ffmpeg, .ffmpeg.txt 등 변종
                    or name.startswith(stem + ".state")     # .state, .state.json 등 변종
                    or name.startswith(stem + ".ytdl")      # .ytdl*
                    or name.startswith(stem + ".part")      # .part*
                    or name.startswith(stem + ".aria2")     # .aria2*
                ):
                    targets.append(full)
        except FileNotFoundError:
            return []
        return targets

    # TMP_ROOT: video_id__* 작업폴더 정리
    def _collect_tmpdirs():
        if not video_id:
            return []
        try:
            tmp_targets = []
            for entry in os.scandir(TMP_ROOT):
                if entry.is_dir() and entry.name.startswith(f"{video_id}_"):
                    tmp_targets.append(os.path.join(TMP_ROOT, entry.name))
            return tmp_targets
        except FileNotFoundError:
            return []

    logger.debug(f"cleanupTmp ENTER prefix='{prefix_path}' video_id='{video_id}'", flush=True)

    # 지수 백오프 기반 재시도 + Windows 강제삭제 폴백
    for attempt in range(max(1, retries)):
        leftover = []
        targets  = _collect_outputs() + _collect_tmpdirs()
        if attempt == 0:
            logger.debug("cleanupTmp initial targets:", targets, flush=True)

        for p in targets:
            q = _win_long(p)
            try:
                if os.path.isdir(q):
                    shutil.rmtree(q, ignore_errors=True)
                else:
                    os.remove(q)
            except Exception as e:
                leftover.append(q)

        if not leftover:
            logger.debug(f"cleanupTmp attempt {attempt+1}: all removed", flush=True)
            break

        # 파이썬 삭제 실패 → Windows 강제 삭제 폴백
        if os.name == 'nt':
            still = []
            for q in leftover:
                try:
                    if os.path.isdir(q):
                        # rmdir /s /q
                        subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", q], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else:
                        # del /f /q
                        subprocess.run(["cmd", "/c", "del", "/f", "/q", q], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    pass
                if os.path.exists(q):
                    still.append(q)
            leftover = still

        if not leftover:
            logger.debug(f"cleanupTmp attempt {attempt+1} (fallback): all removed", flush=True)
            break

        logger.debug(f"cleanupTmp attempt {attempt+1}: leftover -> {leftover}", flush=True)
        # 지수 백오프(AV/인덱서 핸들 해제 대기)
        time.sleep(delay * (1.25 ** attempt))

    logger.debug(f"cleanupTmp LEAVE prefix='{prefix_path}'", flush=True)


# 녹화 진행표시 함수
async def progressTouchLoop(progress_path: str, proc):
    # 시작 즉시 생성
    try:
        with open(progress_path, "w", encoding="utf-8") as f:
            f.write("recording...\n")
    except Exception:
        pass

    try:
        while proc.returncode is None:
            # mtime 갱신으로 탐색기/툴에서 살아있음 표시
            try:
                os.utime(progress_path, None)
            except FileNotFoundError:
                # 누가 지웠으면 다시 만든다
                with open(progress_path, "w", encoding="utf-8") as _f:
                    _f.write("recording...\n")
            await asyncio.sleep(3)
    finally:
        # 종료 시 즉시 삭제
        try:
            if os.path.exists(progress_path):
                os.remove(progress_path)
        except Exception:
            pass


# rename 재시도 함수
async def safeRename(src: str, dst: str, tries: int = 7, delay: float = 1.0):
    for i in range(tries):
        try:
            os.replace(src, dst)
            return True
        except PermissionError as e:
            if getattr(e, "winerror", None) != 32:
                raise
            await asyncio.sleep(delay)
    return False


# 사용자 중지 요청 처리 함수 
async def checkStopRequest(channel_id: str, proc):
    while True:
        await asyncio.sleep(1)
        if recorder_manager.get_is_user_stopped(channel_id):
            logger.debug(f"{channel_id} 중지 요청 – 병합 시그널 전송", flush=True)
            sendInterrupt(proc)
            # 종료 대기/병합/정리는 메인 루틴에서만 수행(레이스 제거)
            break


# 유튜브 병합 후 파일 이동 공통 함수
async def moveAfterProcessingTask(*, mp_enabled: bool, mp_dir: str, prefix_path: str, move_src: str | None,
                                  base_dir: str = base_directory, scan_window_sec: int = 900, settle_sec: float = 5.0, 
                                  retries: int = 8, retry_delay: float = 1.2, channel_id: str | None = None, channel_name: str | None = None):

    # 0) 설정 로깅 및 빠른 실패 사유 노출
    logger.info(f"enabled={mp_enabled} dest='{mp_dir}' prefix='{prefix_path}' src='{move_src}'", flush=True)
    if not mp_enabled:
        logger.info("skip: moveAfterProcessingEnabled=False", flush=True)
        return
    if not mp_dir or not mp_dir.strip():
        logger.info("skip: moveAfterProcessing path is empty", flush=True)
        return

    # 1) 목적지 절대경로화
    dest_dir = mp_dir.strip()
    if not os.path.isabs(dest_dir):
        dest_dir = os.path.join(base_dir, dest_dir)

    # 2) 후보 파일 확보 (우선순위: 인자로 받은 move_src → prefix 확장자 매칭 → 최근 스캔)
    candidate = move_src if (move_src and os.path.exists(move_src)) else None
    if not candidate:
        for ext in (".mp4", ".mkv", ".ts"):
            p = prefix_path + ext
            if os.path.exists(p):
                candidate = p
                break

    if not candidate:
        root_dir = os.path.dirname(prefix_path)
        now = time.time()
        cands = []
        for root in (root_dir, TMP_ROOT):
            for ext in (".mp4", ".mkv", ".ts"):
                cands.extend(glob.glob(os.path.join(root, f"*{ext}")))
        # 최근 파일만
        cands = [p for p in cands if os.path.getmtime(p) >= now - scan_window_sec]
        same_stem = [p for p in cands if os.path.splitext(p)[0] == prefix_path]
        pick = same_stem[0] if same_stem else (max(cands, key=os.path.getmtime) if cands else None)
        if pick and os.path.exists(pick):
            candidate = pick

    if not candidate or not os.path.exists(candidate):
        logger.info(f"no-candidate: prefix='{prefix_path}' window={scan_window_sec}s", flush=True)
        return

    # 3) 같은 폴더면 이동 불필요
    src_dir = os.path.normcase(os.path.abspath(os.path.dirname(candidate)))
    dst_dir = os.path.normcase(os.path.abspath(dest_dir))
    if src_dir == dst_dir:
        logger.info(f"skip: destination equals source dir: {dst_dir}", flush=True)
        return

    # 4) 작업 안정화를 위해 잠깐 대기
    await asyncio.sleep(settle_sec)

    # 5) PermissionError(특히 WinError 32) 등에 대한 재시도 래핑
    for i in range(1, retries + 1):
        try:
            logger.info(f"try {i}/{retries}: '{candidate}' → '{dest_dir}'", flush=True)
            await moveDirectory(candidate, dest_dir)
            logger.info("done", flush=True)

            # 병합 완료 안전망 알림 (파이프/메인 경로에서 놓친 경우)
            try:
                if channel_id and channel_name and last_notified_state.get(channel_id) != "병합완료":
                    sendTelegram(
                        f"<b>{channel_name}</b> 유튜브 <b>병합 완료</b>\n<code>{os.path.basename(candidate)}</code>"
                    )
                    last_notified_state[channel_id] = "병합완료"
            except Exception as _e:
                logger.warning(f"yt merge-done telegram (late-move) failed: {_e}", flush=True)

            return

        except Exception as e:

            # PermissionError면 재시도, 그 외엔 즉시 로그 후 중단
            if isinstance(e, PermissionError) or "used by another process" in str(e).lower():
                await asyncio.sleep(retry_delay)
                continue
            logger.info(f"failed (non-retry): {e}", flush=True)
            return

    logger.info(f"failed: all retries exhausted for '{candidate}'", flush=True)


# 유튜브용 녹화 시작 함수
async def ytStartRecording(channel, recheckInterval: int, filenamePattern: str, moveAfterProcessingEnabled: bool,
                           moveAfterProcessing: str, ycookie_path: str | None, is_user_request: bool = False):

    logger.debug("youtube_recorder loaded from:", __file__, "cleanupTmp id:", id(globals().get("cleanupTmp", None)), flush=True)

    # 0) 쿠키 유효성 (항상 기본값 보장)
    cookies_valid = False

    last_video_id = None

    # 전달된 경로 검사
    if not (isinstance(ycookie_path, str) and os.path.isfile(ycookie_path)):
        ycookie_path = None
    else:
        try:
            cookies_valid, _ = validateCookies(ycookie_path)
        except Exception:
            cookies_valid = False

    # 쿠키가 무효/부재면 최소 CONSENT 쿠키 생성해 폴백
    if not cookies_valid:
        try:
            ycookie_path = ysaveCookies()                 # /json/ycookie.txt 에 작성
            cookies_valid, _ = validateCookies(ycookie_path)
            if cookies_valid:
                logger.info("Minimal CONSENT cookie applied for public live.")
        except Exception as _e:
            logger.warning(f"minimal cookie create failed: {_e}")
            cookies_valid = False
            ycookie_path = None

    hb_task = None  # 하트비트 핸들

    # 1) 채널 동기화
    state_channels = RecorderManager.getChannels() or []
    channel = next((c for c in state_channels if c["id"] == channel["id"]), None)
    if not channel or channel.get("platform") != "youtube":
        return

    channel_id = channel["id"]
    channel_name = channel["name"]

    # 2) 사용자 시작이면 stop 해제
    if is_user_request:
        recorder_manager.set_is_user_stopped(channel_id, False)
    elif recorder_manager.get_is_user_stopped(channel_id):
        return

    # 3) 이미 녹화 중이면 거절
    if recorder_manager.get_status_recording(channel_id) and recorder_manager.get_tasks_process(channel_id):
        return

    try:
        while True:
            hb_task = None

            # 4) 사용자 중지 즉시 탈출
            if recorder_manager.get_is_user_stopped(channel_id):
                recorder_manager.set_status_recording(channel_id, False)
                return

            # 5) 토글 최신화
            current_channels = RecorderManager.getChannels() or []
            curr = next((c for c in current_channels if c.get("id") == channel_id), None) or channel
            rec_enabled = bool(curr.get("record_enabled", True))

            # 6) 라이브 여부 확인
            metadata = await getYoutubeMetadata(curr, ycookie_path)
            is_live = bool(metadata.get("is_live"))
            last_video_id = metadata.get("video_id")

            # 7) 녹화 전 표시: 라이브가 아니면 토글에 따라 예약/대기
            if not is_live:

                if rec_enabled:
                    # 토글 ON → 예약 유지
                    recorder_manager.set_status_recording(channel_id, False)
                    recorder_manager.set_status_reserved(channel_id, True)
                    recorder_manager.recording_remove_start_time(channel_id)

                    # 예약녹화 전환 알림 
                    try:
                        new_state = "예약녹화 중"
                        if last_notified_state.get(channel_id) != new_state:
                            sendTelegram(f"<b>{channel_name}</b> 채널은 <i>예약녹화 중</i>으로 전환되었습니다.")
                            last_notified_state[channel_id] = new_state
                    except Exception as _e:
                        logger.warning(f"yt reserved telegram failed(1): {_e}")

                    # 결정적 지터 대기 블록
                    _base = max(10, int(recheckInterval))
                    _jit  = max(1, int(_base * JITTER_RATIO))
                    _seed = int(hashlib.blake2b(str(channel_id).encode(), digest_size=4).hexdigest(), 16)

                    _phase = _JITTER_PHASE.get(channel_id)
                    if _phase is None:
                        _phase = (_seed % (2 * _jit + 1)) - _jit  # [-_jit, +_jit]
                        _JITTER_PHASE[channel_id] = _phase

                    now = time.monotonic()
                    period = _base
                    k = math.floor((now - (START_MONO + _phase)) / period) + 1
                    next_time = START_MONO + _phase + k * period
                    _sleep = max(1, int(next_time - now))

                    logger.debug(f"{channel_name} 예약 유지. {_sleep}s 후 재탐색(초기위상={_phase:+d}s, 주기={period}s).")
                    await asyncio.sleep(_sleep)
                    continue

                else:
                    # 토글 OFF → 1회성: 예약 보류(대기)
                    recorder_manager.set_status_recording(channel_id, False)
                    recorder_manager.set_status_reserved(channel_id, False)
                    recorder_manager.recording_remove_start_time(channel_id)
                    logger.debug(f"{channel_name} 토글 OFF(1회성). 라이브 미오픈이므로 종료.")
                    break

            # 8) 화질/확장자 계산
            user_q = (curr.get("quality") or "best").strip().lower()
            selected_quality = user_q if re.match(r"^(?:\d+p(?:60)?|best)$", user_q) else "best"

            ch_ext = (curr.get("extension") or "").lower()
            if ch_ext in (".mp4", ".mkv", ".ts"):
                ext = ch_ext
            else:
                m = re.match(r"^(\d+)p", selected_quality or "")
                res_num = int(m.group(1)) if m else 0
                ext = ".mkv" if res_num > 1080 else ".mp4"

            logger.debug(f"ytStartRecording: launch {channel_id} q={selected_quality} cookie={'yes' if cookies_valid else 'no'}")

            # 8-1) 이동 설정을 불리언 정규화
            mp_enabled = toBool(moveAfterProcessingEnabled, default=False)
            mp_dir     = (moveAfterProcessing or "").strip()

            logger.debug(f"moveAfterProcessingEnabled(global)={mp_enabled} moveAfterProcessing(global)='{mp_dir}'", flush=True)

            # 9) ytarchive 명령 생성
            record_cmd, prefix_path, output_path = buildCommand(
                channel=curr,
                output_dir=curr.get("output_dir", "output"),
                quality=selected_quality,
                extension=ext,
                metadata=metadata,
                cookies_valid=cookies_valid,
                filenamePattern=filenamePattern,
                ycookie_path=ycookie_path,
            )

            # 명령 생성 실패 시
            if not output_path:
                recorder_manager.set_status_recording(channel_id, False)
                recorder_manager.clear_tasks_process(channel_id)
                recorder_manager.recording_remove_start_time(channel_id)
                recorder_manager.recording_remove_filename(channel_id)

                if rec_enabled:
                    recorder_manager.set_status_reserved(channel_id, True)
                    await asyncio.sleep(recheckInterval)
                    continue
                else:
                    recorder_manager.set_status_reserved(channel_id, False)
                    logger.debug(f"{channel_name} 토글 OFF(1회성). 명령 생성 실패 후 종료.")
                    break


            logger.debug("ytarchive 실행 명령:", " ".join(shlex.quote(arg) for arg in record_cmd))

            # 10) 환경설정 및 실행
            ffmpeg_dir = os.path.dirname(getFFmpeg())
            env = os.environ.copy()
            env["PATH"] = os.pathsep.join([ffmpeg_dir, env.get("PATH", "")])

            kwargs = {}
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                import os as _posix_os
                kwargs["preexec_fn"] = _posix_os.setsid

            proc = await asyncio.create_subprocess_exec(
                *record_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.path.dirname(prefix_path),
                env=env,
                limit=2 ** 20,
                **kwargs,
            )
            recorder_manager.set_tasks_process(channel_id, proc)
            recorder_manager.recording_set_filename(channel_id, output_path)

            # 진행 표시 파일 루프 시작
            progress_path = prefix_path + ".recording"
            progress_task = asyncio.create_task(progressTouchLoop(progress_path, proc))

            # 11) 프로세스 핸들 확보 후에만 녹화 중으로 승격
            recorder_manager.set_status_recording(channel_id, True)
            recorder_manager.set_status_reserved(channel_id, False)
            recorder_manager.recording_set_start_time(channel_id)
            sendTelegram(f"<b>{channel_name}</b> 채널의 녹화가 시작되었습니다.")

            # 이 회차 시작 시, 과거 병합완료 가드 초기화 + 세션 플래그
            with contextlib.suppress(Exception):
                last_notified_state.pop(channel_id, None)
            merge_notified = False

            # 12) 하트비트 & 파이프 리더
            hb_task = spawnHeartbeat(
                channel_id,
                get_proc=lambda: recorder_manager.get_tasks_process(channel_id),
                interval=12.0,
                probe=_make_youtube_probe(curr, ycookie_path),
            )

            final_q = asyncio.Queue()

            # 파이프 측 이동 콜백
            async def _pipe_side_move(path: str):
                try:
                    if not (mp_enabled and mp_dir):
                        return

                    # 1) 병합 직후 여유
                    logger.info(f"[pipe] detected final: '{path}' (delay 5s before move)", flush=True)
                    await asyncio.sleep(5.0)

                    if not os.path.exists(path):
                        logger.info(f"[pipe] skipped: not exists -> {path}", flush=True)
                        return

                    # 2) 간단한 파일 크기 안정화 체크
                    async def _wait_file_stable(p: str, checks: int = 2, interval: float = 1.0, max_wait: float = 15.0) -> bool:
                        prev = -1
                        stable = 0
                        deadline = time.time() + max_wait
                        while time.time() < deadline:
                            try:
                                size = os.path.getsize(p)
                            except FileNotFoundError:
                                await asyncio.sleep(interval)
                                continue
                            if size == prev:
                                stable += 1
                                if stable >= checks:
                                    return True
                            else:
                                stable = 0
                                prev = size
                            await asyncio.sleep(interval)
                        return False

                    stable_ok = await _wait_file_stable(path, checks=2, interval=1.0, max_wait=15.0)
                    if not stable_ok:
                        logger.info(f"[pipe] warn: size not fully stabilized; proceed anyway", flush=True)

                    logger.info(f"[pipe] try: '{path}' → '{mp_dir}'", flush=True)
                    await moveDirectory(path, mp_dir)   # data_manager 공용 이동 함수 사용
                    logger.info(f"[pipe] done", flush=True)

                    # 병합 완료 알림
                    try:
                        nonlocal merge_notified
                        if not merge_notified:
                            sendTelegram(
                                f"<b>{channel_name}</b> 유튜브 <b>병합 완료</b>\n<code>{os.path.basename(path)}</code>"
                            )
                            merge_notified = True
                            last_notified_state[channel_id] = "병합완료"

                    except Exception as _e:
                        logger.warning(f"yt merge-done telegram failed: {_e}", flush=True)

                except Exception as e:
                    logger.info(f"[pipe] failed: {e}", flush=True)


            # 최종 산출 경로 그대로 사용
            expected_out = output_path or (f"{prefix_path}{extFromQuality(selected_quality)}")

            err_task = asyncio.create_task(
                readPipe(proc.stderr, channel_id, channel_name, final_q,
                         cwd=os.path.dirname(prefix_path), expected_out=expected_out,
                         on_final=_pipe_side_move)
            )
            out_task = asyncio.create_task(
                readPipe(proc.stdout, channel_id, channel_name, final_q,
                         cwd=os.path.dirname(prefix_path), expected_out=expected_out,
                         on_final=_pipe_side_move)
            )
            stop_task = asyncio.create_task(checkStopRequest(channel_id, proc))


            # 13) 프로세스 종료 대기
            logger.debug("await proc.wait() ...", flush=True)
            await proc.wait()
            logger.debug("proc.wait() returned", flush=True)

            # stop 플래그 스냅샷 및 해제
            stop_req_snapshot = recorder_manager.get_is_user_stopped(channel_id)
            # 자연 종료 시 다음 루프/세션에 영향을 주지 않도록 플래그는 내려둡니다.
            recorder_manager.set_is_user_stopped(channel_id, False)

            # 14) 리더 태스크 정리 (타임아웃 + 취소)
            logger.debug("join pipe readers ...", flush=True)
            done, pending = await asyncio.wait({err_task, out_task}, timeout=5.0)

            # 남은 태스크는 취소 후 합류
            for t in pending:
                t.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await t

            # stop 감시 태스크도 정리
            if not stop_task.done():
                stop_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await stop_task
            logger.debug(f"readers joined. done={len(done)} pending_canceled={len(pending)}", flush=True)

            logger.debug("checkpoint A: before progress_task cancel", flush=True)
            if 'progress_task' in locals():
                try:
                    progress_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await asyncio.wait_for(progress_task, timeout=3.0)
                except asyncio.TimeoutError:
                    logger.warning("progress_task cancel timeout; continue", flush=True)

            logger.debug("checkpoint B: before heartbeat cancel", flush=True)
            if hb_task:
                try:
                    await asyncio.wait_for(cancelTaskSafely(hb_task), timeout=3.0)
                except asyncio.TimeoutError:
                    logger.warning("heartbeat cancel timeout; continue", flush=True)
                hb_task = None

            logger.debug("entering step 15 (post-merge handling)", flush=True)

            move_src = None

            # 15-0) 프로세스 종료 보장
            if proc.returncode is None:
                await proc.wait()

            # 15-0b) 그레이스 대기(최대 8초)로 늦은 쓰기 반영 유도
            deadline = time.time() + 8.0
            real_final = None
            while time.time() < deadline:
                if os.path.exists(output_path):
                    move_src = output_path
                    break
                drained = None
                while True:
                    try:
                        drained = final_q.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                if drained and os.path.exists(drained):
                    real_final = drained
                    break
                await asyncio.sleep(0.5)

            # 15-1) 우선순위: 패턴 경로 → pipe → 스캔
            if not move_src:
                if real_final and os.path.exists(real_final):
                    wanted = output_path if not os.path.exists(output_path) else \
                             uniqueFilename(os.path.dirname(output_path), os.path.basename(output_path), add_suffix=True)
                    ok = await safeRename(real_final, wanted)
                    if ok:
                        logger.debug(f"rename -> '{wanted}' (from pipe)", flush=True)
                        move_src = wanted
                if not move_src:
                    root_dir = os.path.dirname(prefix_path)
                    now = time.time()
                    candidates = []
                    for root in (root_dir, TMP_ROOT):
                        for _ext in (".mp4", ".mkv", ".ts"):
                            candidates.extend(glob.glob(os.path.join(root, f"*{_ext}")))
                    candidates = [p for p in candidates if os.path.getmtime(p) >= now - 900]
                    same_stem = [p for p in candidates if os.path.splitext(p)[0] == prefix_path]
                    pick = same_stem[0] if same_stem else (max(candidates, key=os.path.getmtime) if candidates else None)
                    if pick and os.path.exists(pick):
                        wanted = output_path if not os.path.exists(output_path) else \
                                 uniqueFilename(os.path.dirname(output_path), os.path.basename(output_path), add_suffix=True)
                        ok = await safeRename(pick, wanted) if pick != wanted else True
                        if ok:
                            logger.debug(f"adopt scanned -> '{wanted}'", flush=True)
                            move_src = wanted

            # 15-2) cleanup & 진행파일 삭제
            if move_src and os.path.exists(move_src):
                logger.debug(f"call cleanupTmp(after-merge) prefix='{prefix_path}', video_id='{last_video_id}'", flush=True)
                cleanupTmp(prefix_path, last_video_id)
                # 잠깐 쉬었다가(파일 핸들 해제 대기) 한 번 더
                await asyncio.sleep(1.5)
                cleanupTmp(prefix_path, last_video_id)
                # 진행파일 제거
                with contextlib.suppress(Exception):
                    if os.path.exists(progress_path):
                        os.remove(progress_path)

                # 병합된 파일을 설정된 경로로 이동
                if mp_enabled and mp_dir:
                    await moveDirectory(move_src, mp_dir)
                    logger.info(f"파일 {move_src}가 {mp_dir} 폴더로 이동되었습니다.")

                # 병합 완료 알림
                try:
                    if not merge_notified:
                        sendTelegram(
                            f"<b>{channel_name}</b> 유튜브 <b>병합 완료</b>\n<code>{os.path.basename(move_src)}</code>"
                        )

                        merge_notified = True
                        last_notified_state[channel_id] = "병합완료"

                except Exception as _e:
                    logger.warning(f"yt merge-done telegram failed: {_e}")

            else:
                 logger.warning("병합 실패 – Final file 경로를 찾지 못했습니다.")

            # 16) 사후 이동
            await moveAfterProcessingTask(
                  mp_enabled=mp_enabled,
                  mp_dir=mp_dir,
                  prefix_path=prefix_path,
                  move_src=move_src,
                  channel_id=channel_id,
                  channel_name=channel_name,
            )

            # 병합완료 텔레그램 누락 시 한 번 더 시도
            if not merge_notified:
                final_hint = move_src or output_path
                if final_hint and os.path.exists(final_hint):
                    try:
                        sendTelegram(
                            f"<b>{channel_name}</b> 유튜브 <b>병합 완료</b>\n<code>{os.path.basename(final_hint)}</code>"
                        )
                        merge_notified = True
                        last_notified_state[channel_id] = "병합완료"
                    except Exception as _e:
                        logger.warning(f"yt merge-done telegram failed(2nd): {_e}")

            # 17) 세션 종료 컨텍스트 정리
            stop_req = recorder_manager.get_is_user_stopped(channel_id)
            try:
                auto_cfg = (loadConfig() or {}).get("autoRecordingMode", False)
            except Exception:
                auto_cfg = False
            rec_enabled_dbg = bool(curr.get("record_enabled", True))

            logger.info(
                f"[REC-END] {channel_name} auto={auto_cfg} "
                f"enabled={rec_enabled_dbg} stop_requested={stop_req}"
            )

            # 만약 파이프에서 녹화종료를 못 보낸 경우에만 한 번 더 보냄
            try:
                if last_notified_state.get(channel_id) not in ("녹화종료", "병합완료"):
                    dur = recorder_manager.get_recording_duration(channel_id)
                    msg = (
                        f"<b>{channel_name}</b> 녹화가 <b>종료</b>되었습니다. 병합을 시작합니다."
                        + (f" (녹화시간 {dur})" if dur else "")
                        + (f"\n<code>{os.path.basename(output_path)}</code>" if output_path else "")
                    )
                    sendTelegram(msg)
                    last_notified_state[channel_id] = "녹화종료"

            except Exception as _e:
                logger.warning(f"yt record-done telegram failed: {_e}")

            try:
                recorder_manager.set_status_recording(channel_id, False)
                recorder_manager.recording_remove_start_time(channel_id)
                recorder_manager.recording_remove_filename(channel_id)
                recorder_manager.clear_tasks_process(channel_id)

            except Exception as _e:
                logger.warning(f"end-of-session cleanup failed: {_e}")

            if not stop_req:
                recorder_manager.set_is_user_stopped(channel_id, False)

            logger.debug(f"{channel_name} 세션 종료. FSM 후속 전이")

            # 종료 후 분기(지속 감시 vs 종료)
            latest = RecorderManager.getChannels() or []
            latest_ch = next((c for c in latest if c.get("id") == channel_id), None) or curr
            latest_rec_enabled = bool(latest_ch.get("record_enabled", True))

            if recorder_manager.get_is_user_stopped(channel_id):
                recorder_manager.set_status_reserved(channel_id, False)
                logger.debug(f"{channel_name} 사용자 중지로 루프 종료.")
                break

            if latest_rec_enabled:
                recorder_manager.set_status_reserved(channel_id, True)

                # 예약녹화 전환 알림
                try:
                    new_state = "예약녹화 중"
                    if last_notified_state.get(channel_id) != new_state:
                        sendTelegram(f"<b>{channel_name}</b> 채널은 <i>예약녹화 중</i>으로 전환되었습니다.")
                        last_notified_state[channel_id] = new_state
                except Exception as _e:
                    logger.warning(f"yt reserved telegram failed(2): {_e}")

                _base = max(10, int(recheckInterval))
                _jit  = max(1, int(_base * JITTER_RATIO))
                _seed = int(hashlib.blake2b(str(channel_id).encode(), digest_size=4).hexdigest(), 16)

                _phase = _JITTER_PHASE.get(channel_id)
                if _phase is None:
                    _phase = (_seed % (2 * _jit + 1)) - _jit
                    _JITTER_PHASE[channel_id] = _phase

                now = time.monotonic()
                period = _base
                k = math.floor((now - (START_MONO + _phase)) / period) + 1
                next_time = START_MONO + _phase + k * period
                _sleep = max(1, int(next_time - now))

                logger.debug(f"{channel_name} 종료 → 예약 유지. {_sleep}s 후 재탐색(초기위상={_phase:+d}s, 주기={period}s).")
                await asyncio.sleep(_sleep)

                continue

            else:
                recorder_manager.set_status_reserved(channel_id, False)
                logger.debug(f"{channel_name} 토글 OFF(1회성). 종료.")
                break

    except Exception as e:
        logger.error(f"{channel_name} 녹화 중 예외: {e}")

    finally:

        if hb_task:
            await cancelTaskSafely(hb_task)
        with contextlib.suppress(Exception):
            recorder_manager.set_status_recording(channel_id, False)
            recorder_manager.clear_tasks_process(channel_id)
            recorder_manager.recording_remove_start_time(channel_id)
            recorder_manager.recording_remove_filename(channel_id)

        try:
            # 보조 안전망: 최종 산출물이 있을 때 정리 1회 더
            any_final = any(os.path.exists(prefix_path + ext) for ext in (".mp4", ".mkv", ".ts"))
            if any_final:
                logger.debug(f"call cleanupTmp(finally) prefix='{prefix_path}', video_id='{last_video_id}'", flush=True)
                cleanupTmp(prefix_path, last_video_id)

            # 진행파일 삭제 안전망
            with contextlib.suppress(Exception):
                progress_path = prefix_path + ".recording"
                if os.path.exists(progress_path):
                    os.remove(progress_path)

            # 앞 단계에서 이동 누락 시 마지막으로 한 번 더 시도
            try:
                await moveAfterProcessingTask(
                      mp_enabled=mp_enabled,
                      mp_dir=mp_dir,
                      prefix_path=prefix_path,
                      move_src=None,
                      channel_id=channel_id,
                      channel_name=channel_name,
                )

            except Exception as _e:
                logger.warning(f"late-move failed: {_e}")

        except Exception:
            pass

        if is_user_request:
            recorder_manager.set_is_user_stopped(channel_id, False)

        try:
            latest = RecorderManager.getChannels() or []
            latest_ch = next((c for c in latest if c.get("id") == channel_id), None) or {}
            if bool(latest_ch.get("record_enabled", True)):
                if not recorder_manager.get_is_user_stopped(channel_id):
                    recorder_manager.set_status_reserved(channel_id, True)

        except Exception:
            pass


# 유튜브용 녹화 중지 함수
async def ytStopRecording(channel_id: str):
    logger.debug(f"ytStopRecording 시작 - 채널 ID: {channel_id}")

    # 이미 요청이 들어가 있으면 아무 것도 하지 않음
    if recorder_manager.get_is_user_stopped(channel_id):
        return

    # 중지 요청 플래그만 세우고 리턴
    recorder_manager.set_is_user_stopped(channel_id, True)
    logger.debug(f"{channel_id} 중지 요청 플래그 설정 완료")