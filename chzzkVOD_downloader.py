import os
import re
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
import requests
import json

base_dir = os.path.dirname(os.path.abspath(__file__))

VERSION = "치지직/유튜브 VOD 다운로더 CLI v1.0.0a"

# 의존성 파일들 상대경로
def getYtDlp():
    return os.path.join(base_dir, "dependent", "yt-dlp", "yt-dlp.exe")

def getAria2c():
    return os.path.join(base_dir, "dependent", "aria2c", "aria2c.exe")

def getFFmpeg():
    return os.path.join(base_dir, "dependent", "ffmpeg", "bin", "ffmpeg.exe")

def getStreamlink():
    return os.path.join(base_dir, "dependent", "streamlink", "bin", "streamlink.exe")


# 치지직 VOD API URL 상수
CHZZK_VOD_INFO_API = "https://api.chzzk.naver.com/service/v2/videos/{videoNo}"
CHZZK_VOD_URI_API = "https://apis.naver.com/neonplayer/vodplay/v2/playback/{videoId}?key={inKey}"

current_download_process = None


def loadCookies():
    cookie_file = os.path.join(base_dir, "json", "cookie.json")
    if os.path.exists(cookie_file):
        try:
            with open(cookie_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print("쿠키 파일 읽기 오류:", e)
    return {}


def loadYoutubeCookies():
    ycookie_file = os.path.join(base_dir, "json", "ycookie.txt")
    if os.path.exists(ycookie_file):
        return ycookie_file
    else:
        return None


def sanitize_filename(filename: str) -> str:
    base, ext = os.path.splitext(filename) 
    base = base.replace('\u3000', ' ').replace('\u00a0', ' ')
    base = re.sub(r'[\r\n\t]+', '', base)
    forbidden_pattern = r'[\\/:*?"<>|\(\)\{\}]'
    base = re.sub(forbidden_pattern, '_', base)
    base = base.replace('.', '_')
    base = base.strip()
    if not base:
        base = "_"
    if ext and not ext.startswith('.'):
        ext = '.' + ext
    return base + ext


def formatLiveDate(live_open_date_raw: str):
    if not live_open_date_raw:
        return None, None
    try:
        date_part, time_part = live_open_date_raw.split(" ")
    except ValueError:
        date_part = live_open_date_raw.strip()
        time_part = "00:00:00"
    y, m, d = date_part.split("-")
    hh, mm, ss = time_part.split(":")
    recording_time = f"{y[2:]}{m}{d}_{hh}{mm}{ss}"
    start_time = date_part
    return recording_time, start_time


def getCookieHeaders():
    if os.name == 'nt':
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            " AppleWebKit/537.36 (KHTML, like Gecko)"
            " Chrome/98.0.4758.102 Safari/537.36"
        )
    else:
        user_agent = (
            "Mozilla/5.0 (X11; Linux x86_64)"
            " AppleWebKit/537.36 (KHTML, like Gecko)"
            " Chrome/98.0.4758.102 Safari/537.36"
        )
    headers = {
        "User-Agent": user_agent,
        "Referer": "https://chzzk.naver.com/",
        "Accept": "application/json, */*",
        "Origin": "https://chzzk.naver.com"
    }
    cookies = loadCookies()
    if cookies:
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers["Cookie"] = cookie_str
    return headers



def checkDuplicateFile(output_file: str) -> (bool, str):
    if os.path.exists(output_file):
        print(f"파일 '{output_file}'이(가) 이미 존재합니다.")
        while True:
            print("어떻게 하시겠습니까?")
            print("1. 중복파일 덮어쓰기")
            print("2. 해당파일 이어받기")
            print("3. 해당파일 건너뛰기")
            ans = input("번호를 선택하세요 (1/2/3): ").strip()
            if ans == '3':
                print("완성된 파일이 있으므로 건너뜁니다.")
                return False, ""
            elif ans == '1':
                try:
                    os.remove(output_file)
                    print("기존 파일을 삭제하고 재다운로드합니다.")
                except Exception as e:
                    print("파일 삭제 실패:", e)
                    return False, ""
                return True, ""
            elif ans == '2':
                print("이어받기를 시도합니다.")
                return True, "--continue"
            else:
                print("잘못된 입력입니다. 1, 2, 또는 3을 입력해주세요.")
    return True, ""



def getYoutubePlaylistInfo(vod_url: str):
    try:
        cmd = [getYtDlp(), '-J', '--flat-playlist', vod_url]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
        if result.returncode != 0:
            raise Exception(result.stderr)
        data = json.loads(result.stdout)

        playlist_title = data.get('title')  # 또는 data.get('playlist_title')
        entries = data.get('entries', [])
        return playlist_title, len(entries)
    except Exception as e:
        print("[ERROR] 유튜브 재생목록 정보 조회 오류:", e)
        return None, 0


def getPlaylistItems(playlist_url: str):
    cmd = [getYtDlp(), '-J', '--flat-playlist', playlist_url]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
        if result.returncode != 0:
            raise Exception(result.stderr)

        data = json.loads(result.stdout)
        entries = data.get('entries', [])
        video_urls = []

        for e in entries:
            vid_url = e.get('url')
            if vid_url:
                # 보통 "https://www.youtube.com/watch?v=XXXX" 형태
                video_urls.append(vid_url)
        return video_urls
    except Exception as e:
        print("[ERROR] 재생목록 items 조회 오류:", e)
        return []


def getYoutubeQualities(vod_url: str, only_first_in_playlist: bool = False):
    cmd = [getYtDlp(), '-j']
    if only_first_in_playlist:
        # 재생목록이어도 첫 번째 영상만 json으로 뽑기
        cmd.extend(['--playlist-items', '1'])
    cmd.append(vod_url)

    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
        if result.returncode != 0:
            raise Exception(result.stderr)

        lines = result.stdout.strip().splitlines()
        if not lines:
            return None, None

        # 여러 줄이 나올 수 있지만, 첫 번째 줄만 기준으로 처리
        video_info = json.loads(lines[0])

        if 'formats' not in video_info:
            return None, None

        qualities = []
        seen_labels = set()

        for fmt in video_info.get("formats", []):
            height_val = fmt.get("height") or 0
            if height_val < 360:
                continue

            fps_val = round(fmt.get("fps", 0))
            if fps_val not in [30, 60]:
                continue

            if fmt.get("ext") != "mp4":
                continue

            vcodec_raw = (fmt.get("vcodec") or "").lower()
            if vcodec_raw.startswith("avc1"):
                vcodec_label = "H264"
            elif vcodec_raw.startswith("vp09"):
                vcodec_label = "VP9"
            elif vcodec_raw.startswith("av01"):
                vcodec_label = "AV1"
            else:
                vcodec_label = "unknown"

            label = f"{height_val}p{fps_val}"
            if vcodec_label != "unknown":
                label += f" {vcodec_label}"

            if label in seen_labels:
                continue
            seen_labels.add(label)

            qualities.append({
                'id': fmt.get('format_id'),
                'quality': label,
                'ext': fmt.get('ext'),
                'filesize': fmt.get('filesize') or 0
            })

        return qualities, video_info

    except Exception as e:
        print(f"[ERROR] 유튜브 메타데이터 조회 오류: {e}")
        return None, None



def getVODQualities(vod_url: str):
    vod_info = None
    qualities = None

    if "chzzk.naver.com/video/" in vod_url:
        parts = vod_url.rstrip("/").split("/")
        videoNo = parts[-1]
        info_api_url = CHZZK_VOD_INFO_API.format(videoNo=videoNo)
        headers = getCookieHeaders()
        r = requests.get(info_api_url, headers=headers, timeout=10)
        r.raise_for_status()
        info = r.json()
        if info.get("code") != 200:
            raise Exception("VOD info API 오류: " + str(info.get("message")))
        vod_info = info.get("content", {})
        if not vod_info:
            return None, None

        # HLS 분기: inKey가 없는 경우
        if vod_info.get("inKey") is None:
            live_rewind_json_str = vod_info.get("liveRewindPlaybackJson")
            if not live_rewind_json_str:
                raise Exception("liveRewindPlaybackJson 정보가 없습니다.")
            live_data = json.loads(live_rewind_json_str)
            if "media" not in live_data or not live_data["media"]:
                raise Exception("HLS 미디어 정보가 없습니다.")
            media_entry = live_data["media"][0]
            encoding_tracks = media_entry.get("encodingTrack", [])
            q_list = []
            for track in encoding_tracks:
                quality_label = track.get("encodingTrackId")
                q_list.append({
                    'id': quality_label,
                    'quality': quality_label,
                    'bandwidth': track.get("videoBitRate"),
                    'width': track.get("videoWidth"),
                    'height': track.get("videoHeight"),
                    'frameRate': track.get("videoFrameRate")
                })
            qualities = q_list
        else:
            # DASH 분기: inKey가 존재하면 DASH MPD를 파싱
            videoId = vod_info.get("videoId")
            inKey = vod_info.get("inKey")
            if not videoId or not inKey:
                raise Exception("필수 videoId 또는 inKey 값이 없습니다.")
            mpd_url = CHZZK_VOD_URI_API.format(videoId=videoId, inKey=inKey)
            headers2 = getCookieHeaders()
            headers2["Accept"] = "application/dash+xml, application/xml, */*"
            r2 = requests.get(mpd_url, headers=headers2, timeout=10)
            r2.raise_for_status()
            mpd_content = r2.content.strip()
            root = ET.fromstring(mpd_content)
            ns = {'mpd': 'urn:mpeg:dash:schema:mpd:2011', 'nvod': 'urn:naver:vod:2020'}
            q_list = []
            for adaptation in root.findall('.//mpd:AdaptationSet', ns):
                mimeType = adaptation.get('mimeType')
                if mimeType and "video/mp4" in mimeType:
                    for rep in adaptation.findall('mpd:Representation', ns):
                        rep_id = rep.get('id')
                        bandwidth = rep.get('bandwidth')
                        width = rep.get('width')
                        height = rep.get('height')
                        frameRate = rep.get('frameRate')
                        quality_label = rep.find("nvod:Label[@kind='qualityId']", ns)
                        quality_value = quality_label.text if quality_label is not None else rep_id
                        baseurl_elem = rep.find("{urn:mpeg:dash:schema:mpd:2011}BaseURL")
                        baseurl = baseurl_elem.text.strip() if baseurl_elem is not None else ""
                        q_list.append({
                            'id': rep_id,
                            'quality': quality_value,
                            'bandwidth': bandwidth,
                            'width': width,
                            'height': height,
                            'frameRate': frameRate,
                            'baseurl': baseurl
                        })
                    break
            qualities = q_list
    else:
        return None, None

    return qualities, vod_info


def getVODUrl(vod_url: str, quality: str = None) -> str:
    if "chzzk.naver.com/video/" in vod_url:
        parts = vod_url.rstrip("/").split("/")
        videoNo = parts[-1]
        info_api_url = CHZZK_VOD_INFO_API.format(videoNo=videoNo)
        headers = getCookieHeaders()
        try:
            r = requests.get(info_api_url, headers=headers, timeout=10)
            r.raise_for_status()
        except Exception as e:
            raise Exception(f"VOD 정보 API 호출 실패: {e}")
        info = r.json()
        if info.get("code") != 200:
            raise Exception("VOD info API 오류: " + str(info.get("message")))
        vod_info = info.get("content", {})

        if vod_info.get("inKey") is None:
            live_rewind_json_str = vod_info.get("liveRewindPlaybackJson")
            if not live_rewind_json_str:
                raise Exception("liveRewindPlaybackJson 정보가 없습니다.")
            live_data = json.loads(live_rewind_json_str)
            if "media" not in live_data or not live_data["media"]:
                raise Exception("HLS 미디어 정보가 없습니다.")
            return live_data["media"][0].get("path")
        else:
            videoId = vod_info.get("videoId")
            inKey = vod_info.get("inKey")
            if not videoId or not inKey:
                raise Exception("필수 videoId 또는 inKey 값이 없습니다.")
            mpd_url = CHZZK_VOD_URI_API.format(videoId=videoId, inKey=inKey)
            headers2 = getCookieHeaders()
            headers2["Accept"] = "application/dash+xml, application/xml, */*"
            r2 = requests.get(mpd_url, headers=headers2, timeout=10)
            r2.raise_for_status()
            mpd_content = r2.content.strip()
            root = ET.fromstring(mpd_content)
            ns = {'mpd': 'urn:mpeg:dash:schema:mpd:2011', 'nvod': 'urn:naver:vod:2020'}
            if not quality:
                raise Exception("다운로드할 품질이 지정되지 않았습니다. (예: 1080p, 720p, 144p)")
            match = re.search(r'(\d+)', quality)
            if match:
                desired_quality = match.group(1)
            else:
                raise Exception("올바른 품질 정보가 전달되지 않았습니다.")
            selected_base_url = None
            for adaptation in root.findall('.//mpd:AdaptationSet', ns):
                mimeType = adaptation.get('mimeType')
                if mimeType and "video/mp4" in mimeType:
                    for rep in adaptation.findall('mpd:Representation', ns):
                        res_elem = rep.find("nvod:Label[@kind='resolution']", ns)
                        rep_resolution = res_elem.text if res_elem is not None else rep.get('height')
                        if rep_resolution == desired_quality:
                            baseurl_elem = rep.find('mpd:BaseURL', ns)
                            if baseurl_elem is not None:
                                selected_base_url = baseurl_elem.text.strip()
                                break
                    if selected_base_url:
                        break
            if not selected_base_url:
                raise Exception("원하는 품질의 BaseURL을 찾을 수 없습니다.")
            return selected_base_url
    else:
        return vod_url


def downloadVOD(vod_url: str, quality: str, output_folder: str, auto_filename: str, speed_option: str, download_section: str = None):
    global current_download_process

    safe_name   = sanitize_filename(auto_filename)
    output_file = os.path.join(output_folder, safe_name)
    aria2c_path = getAria2c()
    
    # 중복 파일 처리
    proceed, _ = checkDuplicateFile(output_file)
    if not proceed:
        return

    vod_info = None
    if "chzzk.naver.com/video/" in vod_url:
        parts = vod_url.rstrip("/").split("/")
        videoNo = parts[-1]
        info_api_url = CHZZK_VOD_INFO_API.format(videoNo=videoNo)
        headers = getCookieHeaders()
        try:
            r = requests.get(info_api_url, headers=headers, timeout=10)
            r.raise_for_status()
            info = r.json()
            if info.get("code") != 200:
                raise Exception("VOD info API 오류: " + str(info.get("message")))
            vod_info = info.get("content", {})
        except Exception as e:
            raise Exception(f"VOD 정보 API 호출 실패: {e}")

    #HLS 분기
    if vod_info.get("inKey") is None:
        hls_url = getVODUrl(vod_url)
        streamlink_cmd = [
            getStreamlink(),
            hls_url,
            quality,
            "--stdout"
        ]

        print("\n[INFO] 치지직 빠른 다시보기 => streamlink+ffmpeg 전체 다운로드")
        print("streamlink CMD:", " ".join(streamlink_cmd))
        ffmpeg_cmd = [
            getFFmpeg(),
            "-i", "pipe:0",
            "-c", "copy",
            "-y",
            "-stats",
            "-loglevel", "info",
            output_file
        ]

        print("ffmpeg CMD:", " ".join(ffmpeg_cmd), "\n")
        p_streamlink = subprocess.Popen(streamlink_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        p_ffmpeg = subprocess.Popen(ffmpeg_cmd, stdin=p_streamlink.stdout, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        p_streamlink.stdout.close()

        def read_streamlink_stderr():
            while True:
                line = p_streamlink.stderr.readline()
                if not line:
                    break
                print("[STREAMLINK]", line, end="")

        def read_ffmpeg_stderr():
            while True:
                line = p_ffmpeg.stderr.readline()
                if not line:
                    break
                print("[FFMPEG]", line, end="")

        t_sl = threading.Thread(target=read_streamlink_stderr, daemon=True)
        t_ff = threading.Thread(target=read_ffmpeg_stderr, daemon=True)
        t_sl.start()
        t_ff.start()
        p_ffmpeg.wait()
        p_streamlink.wait()
        time.sleep(0.5)

        print("[INFO] 치지직 빠른 다시보기 다운로드 완료. 파일을 확인하세요.\n")

    # DASH MPD 분기        
    else:
        qualities, _ = getVODQualities(vod_url)
        selected_rep = None
        for rep in qualities:
            if rep.get('id') == quality:
                selected_rep = rep
                break

        if not selected_rep or not selected_rep.get('baseurl'):
            raise Exception("선택한 품질의 다운로드 URL(BaseURL)이 없습니다.")

        download_url = selected_rep['baseurl']

        print(f"\n[INFO] 선택한 품질의 BaseURL: {download_url}")

        if download_section:
            try:
                start_section, end_section = download_section.split("~")
            except Exception as e:
                raise Exception("download_section 형식이 올바르지 않습니다. (예: 00:10:00~00:20:00)")
            def hms_to_seconds(hms):
                h, m, s = map(int, hms.split(':'))
                return h * 3600 + m * 60 + s
            start_seconds = hms_to_seconds(start_section)
            end_seconds = hms_to_seconds(end_section)

            if end_seconds <= start_seconds:
                raise Exception("구간 다운로드: 종료 시간이 시작 시간보다 작거나 같습니다.")

            duration = end_seconds - start_seconds

            cmd = [
                getFFmpeg(),
                "-ss", start_section,
                "-i", download_url,
                "-t", str(duration),
                "-c", "copy",
                "-y", output_file
            ]
            print("\n[INFO] 치지직 VOD 구간 다운로드: ffmpeg 직접 다운로드")
            print(" ".join(cmd), "\n")

            current_download_process = subprocess.Popen(cmd)
            current_download_process.wait()

        else:
            headers = getCookieHeaders()
            cookie_str = headers.get("Cookie", "")
            user_agent_str = headers.get("User-Agent", "")
            referer_str = headers.get("Referer", "")

            downloader_args_mapping = {
                "100%": ["-x", "16", "-s", "16", "-k", "1M"],
                "75%":  ["-x", "12", "-s", "12", "-k", "1M"],
                "50%":  ["-x", "8", "-s", "8", "-k", "1M"],
                "25%":  ["-x", "4", "-s", "4", "-k", "1M"],
                "분할 없음": ["-x", "1", "-s", "1", "-k", "1M"]
            }

            aria_args = downloader_args_mapping.get(speed_option, ["-x", "16", "-s", "16", "-k", "1M"])
            aria_args.append("--file-allocation=none")

            cmd = [
                getAria2c(),
                *aria_args,
                "--file-allocation=none",
                "-d", output_folder,
                "-o", safe_name,
            ]

            if cookie_str:
                cmd += ["--header", f"Cookie: {cookie_str}"]

            if user_agent_str:
                cmd += ["--header", f"User-Agent: {user_agent_str}"]

            if referer_str:
                cmd += ["--header", f"Referer: {referer_str}"]

            cmd.append(download_url)

            print("\n[INFO] 치지직 VOD 전체 다운로드: aria2c 직접 다운로드")
            print(" ".join(cmd), "\n")

            current_download_process = subprocess.Popen(cmd)
            current_download_process.wait()

        print("[INFO] 치지직 VOD 다운로드 완료. 파일을 확인해주세요.\n")



def downloadMultiVOD():
    vod_list = []

    # 1) 치지직 VOD URL 여러 개 입력받기
    while True:
        inp = input("치지직 VOD URL 입력 (종료하려면 엔터): ").strip()
        if not inp:
            break
        if "chzzk.naver.com/video/" not in inp:
            print("치지직 VOD 주소만 입력 가능합니다.")
            continue
        vod_list.append(inp)

        # 추가로 입력할지 여부 확인
        more = input("다운로드할 치지직 VOD URL을 추가하시겠습니까? (y 혹은 n 입력): ").strip().lower()
        if more != 'y':
            break

    if not vod_list:
        print("입력된 VOD가 없어 모드를 종료합니다.")
        return

    # 2) 각 VOD 마다 HLS인지 DASH인지 확인
    hls_list = []
    dash_list = []
    for vod_url in vod_list:
        try:
            qualities, vod_info = getVODQualities(vod_url)
            if not qualities or not vod_info:
                print(f"[WARNING] 품질 정보를 가져올 수 없는 URL: {vod_url}")
                continue

            # HLS = inKey가 None / DASH = inKey 존재
            if vod_info.get("inKey") is None:
                hls_list.append(vod_url)
            else:
                dash_list.append(vod_url)
        except Exception as e:
            print(f"[ERROR] getVODQualities() 실패 URL: {vod_url}, 에러: {e}")

    if not hls_list and not dash_list:
        print("다운로드 가능한 VOD가 없습니다.")
        return

    # 3) 사용자에게 '대표 품질' & 분할옵션 받아오기 (HLS / DASH 각기 따로)
    selected_hls_quality = None
    selected_dash_quality = None
    dash_speed_option = None

    # (3-1) HLS용 대표 품질
    if hls_list:
        # HLS용 임의의 VOD 하나를 골라서 품질 리스트를 구해 사용자에게 보여주기
        sample_url = hls_list[0]
        q, vinfo = getVODQualities(sample_url)
        if q:
            print("\n[빠른 다시보기VOD(HLS) 대표 품질 선택] (예: 360p, 720p, 1080p 등)")
            for idx, item in enumerate(q):
                print(f"{idx+1}. {item['quality']} (ID: {item['id']})")
            while True:
                c = input("HLS 대표 품질 번호 선택: ").strip()
                try:
                    c_int = int(c)
                    if 1 <= c_int <= len(q):
                        selected_hls_quality = q[c_int - 1]['id']
                        break
                except:
                    pass
                print("잘못된 입력입니다.")
        else:
            print("[WARNING] HLS 품질 정보를 가져오지 못했습니다. 기본 720p 처리")
            selected_hls_quality = "720p"
        # HLS는 구간다운로드 X, 분할다운로드 없음

    # (3-2) DASH용 대표 품질 + 분할옵션
    if dash_list:
        sample_url = dash_list[0]
        q, vinfo = getVODQualities(sample_url)
        if q:
            print("\n[인코딩 완료 다시보기 VOD(DASH) 대표 품질 선택]")
            for idx, item in enumerate(q):
                # 예: PD_1080P_1920_8000_192 (ID: PD_1080P_1920_8000_192)
                print(f"{idx+1}. {item['quality']} (ID: {item['id']})")
            while True:
                c = input("DASH 대표 품질 번호 선택: ").strip()
                try:
                    c_int = int(c)
                    if 1 <= c_int <= len(q):
                        selected_dash_quality = q[c_int - 1]['id']
                        break
                except:
                    pass
                print("잘못된 입력입니다.")
        else:
            print("[WARNING] DASH 품질 정보를 가져오지 못했습니다. 기본 720p 처리")
            selected_dash_quality = "PD_720P_1280_4000_192"

        # 분할 다운로드(aria2c) 옵션 (예: 100%, 75% 등)
        print("\n[DASH 다운로드 분할 옵션 선택]")
        print("1) 100% (16분할)")
        print("2) 75% (12분할)")
        print("3) 50% (8분할)")
        print("4) 25% (4분할)")
        print("5) 분할 없음 (1)")

        while True:
            c = input("번호 선택: ").strip()
            if c == '1':
                dash_speed_option = "100%"
                break
            elif c == '2':
                dash_speed_option = "75%"
                break
            elif c == '3':
                dash_speed_option = "50%"
                break
            elif c == '4':
                dash_speed_option = "25%"
                break
            elif c == '5':
                dash_speed_option = "분할 없음"
                break
            else:
                print("1~5 중에서 골라주세요.")

    # 4) 파일명 옵션(1/2) + 다운로드 폴더 경로
    print("\n파일명 옵션 선택:")
    print("1. [YYMMDD_hhmmss] 채널명 영상제목.mp4")
    print("2. [YYYY-MM-DD] 채널명 영상제목.mp4")
    file_opt = input("옵션 번호 (1/2): ").strip()
    if file_opt not in ['1', '2']:
        file_opt = '1'

    output_folder = ""
    while True:
        output_folder = input("\n다운로드 받을 폴더 경로: ").strip()
        if not output_folder:
            print("다운로드 경로를 입력하세요.")
            continue
        if not os.path.exists(output_folder):
            try:
                os.makedirs(output_folder)
                print(f"폴더가 생성되었습니다: {output_folder}")
            except Exception as e:
                print("폴더 생성 실패:", e)
                continue
        break

    # 5) 각 URL 다운로드 수행 (순차)
    print("\n===== 입력된 치지직 VOD들을 순서대로 다운로드합니다. =====\n")
    for vod_url in vod_list:
        try:
            qualities, vod_info = getVODQualities(vod_url)
            if not (qualities and vod_info):
                print(f"[SKIP] 품질 정보 없음: {vod_url}")
                continue

            # 파일명 자동 생성
            live_open_date_raw = vod_info.get("liveOpenDate", "")
            recording_time, start_time = formatLiveDate(live_open_date_raw)
            channel_info = vod_info.get("channel", {}) or {}
            channelName = channel_info.get("channelName") or ""
            videoTitle_raw = vod_info.get("videoTitle", "")
            video_title = videoTitle_raw.strip()

            if file_opt == '2':
                raw_name     = f"[{start_time}] {channelName} {video_title}.mp4"
            else:
                raw_name     = f"[{recording_time}] {channelName} {video_title}.mp4"

            auto_filename = sanitize_filename(raw_name)

            # HLS vs DASH 구분
            if vod_info.get("inKey") is None:
                # HLS
                use_quality = selected_hls_quality or "720p"
                speed_option = "nolimit"  # HLS는 분할 X
            else:
                # DASH
                use_quality = selected_dash_quality or "PD_720P_1280_4000_192"
                speed_option = dash_speed_option or "100%"  # 디폴트

            print(f"\n--- 다운로드 시작: {vod_url}")
            print(f"    품질: {use_quality}, 분할옵션: {speed_option}")
            print(f"    파일명: {auto_filename}")

            # 구간 다운로드는 지원 X
            downloadVOD(
                vod_url=vod_url,
                quality=use_quality,
                output_folder=output_folder,
                auto_filename=auto_filename,
                speed_option=speed_option,
                download_section=None  # 구간X
            )
        except Exception as e:
            print(f"[ERROR] 다운로드 실패: {vod_url}, 사유: {e}")

    print("\n=== 모든 VOD 순차 다운로드를 마쳤습니다. ===\n")
    input("계속하려면 엔터를 누르세요.")



def downloadYoutube(vod_url: str, format_id: str, output_folder: str, base_filename: str, speedLimit: str, download_section: str = None):
    if base_filename.lower().endswith(".mp4"):
        base_filename = base_filename[:-4]

    ffmpeg_path = getFFmpeg()
    youtube_cookie_file = loadYoutubeCookies()
    output_file = os.path.join(output_folder, sanitize_filename(base_filename))

    # 중복 파일 처리
    proceed, resume_option = checkDuplicateFile(output_file)
    if not proceed:
        return

    # 출력 경로
    output_file = os.path.join(output_folder, sanitize_filename(base_filename))

    cmd = [
        getYtDlp(),
        vod_url,
        '-f', f'{format_id}+bestaudio',
        '-o', output_file,
        '--merge-output-format', 'mkv',
        '--ffmpeg-location', ffmpeg_path,
        '--postprocessor-args', '-loglevel error'
    ]

    if youtube_cookie_file:
        cmd.extend(["--cookies", youtube_cookie_file])

    if resume_option:
        cmd.append(resume_option)

    if download_section:
        time_arg = download_section.replace("~", "-")
        if not time_arg.startswith("*"):
            time_arg = "*" + time_arg
        cmd.extend(["--download-sections", time_arg])

    if speedLimit:
        cmd.extend(['--limit-rate', speedLimit])

    print("\n[INFO] 유튜브 영상 다운로드: yt-dlp 명령어")
    print(" ".join(cmd), "\n")
    process = subprocess.Popen(cmd)
    process.wait()
    print("[INFO] 유튜브 영상 다운로드 완료.\n")


def downloadYoutubePlaylist(playlist_url: str, output_folder: str, speedLimit: str, selected_quality: str = None):
    ffmpeg_path = getFFmpeg()
    youtube_cookie_file = loadYoutubeCookies()

    # (1) 재생목록 이름 구하기
    playlist_title, _ = getYoutubePlaylistInfo(playlist_url)
    if not playlist_title:
        playlist_title = "재생목록"
    subfolder_name = f"[재생목록] {playlist_title}"
    subfolder_name = sanitize_filename(subfolder_name)
    final_output_dir = os.path.join(output_folder, subfolder_name)
    if not os.path.exists(final_output_dir):
        os.makedirs(final_output_dir, exist_ok=True)

    # (2) 대표 품질 선택 (selected_quality이 None이면 첫 영상 기준으로 선택)
    if selected_quality is None:
        first_qualities, first_info = getYoutubeQualities(playlist_url, only_first_in_playlist=True)
        if first_qualities and len(first_qualities) > 0:
            print("\n사용 가능한 유튜브 (첫 번째 영상) 화질 목록:")
            for idx, q in enumerate(first_qualities):
                print(f"{idx+1}. {q['quality']} (ID: {q['id']})")
            while True:
                choice = input("\n대표로 사용할 품질 번호를 선택하세요(엔터시 best): ").strip()
                if not choice:
                    print("특정 품질을 선택하지 않았습니다. (bestvideo+bestaudio)")
                    selected_quality = None
                    break
                try:
                    c_int = int(choice)
                    if 1 <= c_int <= len(first_qualities):
                        selected_quality = first_qualities[c_int - 1]['id']
                        break
                except:
                    pass
                print("잘못된 입력입니다. 다시 선택해주세요.")
        else:
            print("첫 번째 영상의 화질 정보를 가져올 수 없습니다. (bestvideo+bestaudio로 진행)")
            selected_quality = None

    # (3) 재생목록 모든 영상 URL 추출
    all_items = getPlaylistItems(playlist_url)
    if not all_items:
        print("[ERROR] 재생목록에 영상이 없습니다.")
        return

    # (4) 각 영상 반복 다운로드 (downloadYoutube 내부에서 중복 파일 처리가 적용됨)
    for idx, video_url in enumerate(all_items, start=1):
        print(f"\n=== [재생목록 영상 {idx}/{len(all_items)}] 다운로드 시도 중 ===\n")
        v_qualities, v_info = getYoutubeQualities(video_url, only_first_in_playlist=False)
        if not v_qualities or len(v_qualities) == 0 or not v_info:
            print("[WARN] 이 영상의 품질 정보를 가져오지 못했습니다. 건너뜁니다.")
            continue

        if selected_quality:
            found = any(q['id'] == selected_quality for q in v_qualities)
            if found:
                ch_name = v_info.get("uploader", "")
                vid_title = (v_info.get("title") or "").strip()
                base_name = f"{ch_name} {vid_title}" if ch_name else vid_title
                downloadYoutube(
                    vod_url=video_url,
                    format_id=selected_quality,
                    output_folder=final_output_dir,
                    base_filename=base_name,
                    speedLimit=speedLimit
                )
                continue
            else:
                print("\n[INFO] 이 영상은 대표로 선택한 품질을 지원하지 않습니다.\n")

        # 대표 품질이 없거나 지원하지 않으면, 해당 영상에 대해 다시 사용자에게 품질 선택 안내
        print("이 영상 전용으로, 사용 가능한 품질을 다시 표시합니다.")
        for i2, q2 in enumerate(v_qualities):
            print(f"{i2+1}. {q2['quality']} (ID: {q2['id']})")
        new_format = None
        while True:
            c = input("원하는 품질 번호를 선택하세요(엔터시 best): ").strip()
            if not c:
                print("특정 품질을 선택하지 않았습니다. (bestvideo+bestaudio)")
                new_format = None
                break
            try:
                c_int = int(c)
                if 1 <= c_int <= len(v_qualities):
                    new_format = v_qualities[c_int - 1]['id']
                    break
            except:
                pass
            print("잘못된 입력입니다. 다시 선택해주세요.")

        ch_name = v_info.get("uploader", "")
        vid_title = (v_info.get("title") or "").strip()
        base_name = f"{ch_name} {vid_title}" if ch_name else vid_title

        downloadYoutube(
            vod_url=video_url,
            format_id=(new_format if new_format else "bestvideo"),
            output_folder=final_output_dir,
            base_filename=base_name,
            speedLimit=speedLimit
        )
    print("\n[INFO] 재생목록의 모든 영상 다운로드를 마쳤습니다.\n")


def main():
    print("==== {} ====\n".format(VERSION))

    # 모드 선택
    print("1) 다중 치지직 VOD 순차 다운로드 모드")
    print("   → 다수의 치지직 VOD URL을 한 번에 입력받아 순차적으로 자동 다운로드")
    print()
    print("2) 단일 다운로드 모드")
    print("   → 단일 치지직 다시보기VOD / 유튜브 영상 / 유튜브 재생목록 다운로드")
    print()

    mode_choice = input("원하는 모드를 선택하세요: (1 혹은 2 입력) ").strip()
    if mode_choice == '1':
        downloadMultiVOD()
        return
    else:

        while True:
            print("==== 영상 다운로드 (CLI 버전) ====\n")
            vod_url = input("영상 주소 (예: https://chzzk.naver.com/video/1234567 또는 https://www.youtube.com/watch?v=xxxx): ").strip()
            if not vod_url:
                print("주소를 입력해야 합니다.")
                continue

            is_youtube = ("youtube.com" in vod_url or "youtu.be" in vod_url)
            is_playlist = (is_youtube and "list=" in vod_url)

            # (1) 유튜브 재생목록
            if is_playlist:
                print("\n[감지] 유튜브 재생목록 주소로 확인되었습니다.\n")

                while True:
                    output_folder = input("다운로드 폴더 경로(예: C:/Downloads): ").strip()
                    if not output_folder:
                        print("다운로드 경로를 입력하세요.")
                        continue
                    if not os.path.exists(output_folder):
                        try:
                            os.makedirs(output_folder)
                            print(f"폴더가 생성되었습니다: {output_folder}")
                        except Exception as e:
                            print("폴더 생성 실패:", e)
                            continue
                    break

                speed_limit = input("다운로드 속도 제한(예: 2M, 제한없음: Enter): ").strip()
                if speed_limit == "":
                    speed_limit = None

                confirm = input("재생목록 전체를 다운로드하시겠습니까? (y 혹은 n 입력): ").strip().lower()
                if confirm != "y":
                    print("취소되었습니다.")
                    continue

                # (2) downloadYoutubePlaylist 호출
                try:
                    downloadYoutubePlaylist(
                        playlist_url=vod_url,
                        output_folder=output_folder,
                        speedLimit=speed_limit,
                        selected_quality=None  # None이면 내부에서 품질선택
                    )
                except Exception as e:
                    print("재생목록 다운로드 중 오류 발생:", e)
                    continue

            # (2) 유튜브 단일 영상
            elif is_youtube:
                qualities, video_info = getYoutubeQualities(vod_url)
                if not qualities or len(qualities) == 0:
                    print("유튜브 영상의 품질 정보를 가져올 수 없습니다.")
                    input("계속하려면 Enter를 누르세요.")
                    continue

                print("\n사용 가능한 유튜브 품질:")
                for idx, q in enumerate(qualities):
                    print(f"{idx+1}. {q['quality']} (ID: {q['id']})")
                while True:
                    choice = input("원하는 품질 번호를 선택하세요: ").strip()
                    if not choice:
                        print("값을 입력해야 합니다.")
                        continue
                    try:
                        choice_int = int(choice)
                        if choice_int < 1 or choice_int > len(qualities):
                            print("잘못된 선택입니다.")
                            continue
                    except ValueError:
                        print("숫자를 입력하세요.")
                        continue
                    selected_quality = qualities[choice_int - 1]['id']
                    break

                while True:
                    output_folder = input("다운로드 받을 폴더 경로 (예: C:/Downloads): ").strip()
                    if not output_folder:
                        print("다운로드 경로를 입력하세요.")
                        continue
                    if not os.path.exists(output_folder):
                        try:
                            os.makedirs(output_folder)
                            print(f"폴더가 생성되었습니다: {output_folder}")
                        except Exception as e:
                            print("폴더 생성 실패:", e)
                            continue
                    break

                channel_name = video_info.get("uploader", "")
                video_title = (video_info.get("title") or "").strip()

                if channel_name:
                    combined_name = f"{channel_name} {video_title}"
                else:
                    combined_name = video_title

                auto_filename = sanitize_filename(combined_name)
                print("\n자동 생성 파일명:", auto_filename)

                download_section = input("다운로드 구간 (00:00:00~00:00:00, 전체: Enter): ").strip()
                if download_section == "":
                    download_section = None

                speed_limit = input("다운로드 속도 제한 (예: 2M, 제한없음: Enter): ").strip()
                if speed_limit == "":
                    speed_limit = None

                print("\n최종 정보 확인:")
                print("영상 URL:", vod_url)
                print("품질 ID:", selected_quality)
                print("폴더:", output_folder)
                print("파일명:", auto_filename)
                print("구간:", download_section if download_section else "전체")
                print("속도 제한:", speed_limit if speed_limit else "제한없음")
                confirm = input("다운로드를 시작하시겠습니까? (y 혹은 n 입력): ").strip().lower()
                if confirm != "y":
                    print("취소되었습니다.")
                    input("계속하려면 Enter를 누르세요.")
                    continue

                try:
                    downloadYoutube(
                        vod_url, 
                        selected_quality, 
                        output_folder, 
                        auto_filename, 
                        speed_limit, 
                        download_section
                    )
                except Exception as e:
                    print("유튜브 다운로드 중 오류 발생:", e)
                    input("계속하려면 Enter를 누르세요.")
                    continue

            # 치지직 VOD 분기 (유튜브가 아닌 경우)
            else:
                try:
                    qualities, vod_info = getVODQualities(vod_url)
                except Exception as e:
                    err_msg = str(e)
                    if "cookie" in err_msg:
                        print("쿠키 값이 없거나 만료되었습니다.")
                    else:
                        print("품질 정보를 가져오는 중 오류 발생:", e)
                    input("계속하려면 Enter를 누르세요.")
                    continue

                if not qualities or len(qualities) == 0:
                    print("사용 가능한 품질 정보를 찾지 못했습니다.")
                    input("계속하려면 Enter를 누르세요.")
                    continue

                vod_status = vod_info.get("vodStatus") if vod_info else ""
                live_open_date_raw = vod_info.get("liveOpenDate", "")
                recording_time, start_time = formatLiveDate(live_open_date_raw)
                channel_info = vod_info.get("channel", {}) or {}
                channelName = channel_info.get("channelName") or ""
                videoTitle_raw = vod_info.get("videoTitle", "")
                video_title = videoTitle_raw.strip()

                print("\n파일명 옵션 선택:")
                print("1. [{}] {} {}".format(recording_time, channelName, video_title))
                print("2. [{}] {} {}".format(start_time, channelName, video_title))
                option = input("옵션 번호를 선택하세요 (1 또는 2): ").strip()
                if option == "2":
                    auto_filename = f"[{start_time}] {channelName} {video_title}.mp4"
                else:
                    auto_filename = f"[{recording_time}] {channelName} {video_title}.mp4"
                auto_filename = sanitize_filename(auto_filename)
                print("\n자동 생성 파일명:", auto_filename)

                print("\n사용 가능한 품질:")
                for idx, q in enumerate(qualities):
                    print(f"{idx+1}. {q['quality']} (ID: {q['id']})")
                while True:
                    choice = input("원하는 품질 번호를 선택하세요: ").strip()
                    if not choice:
                        print("값을 입력해야 합니다.")
                        continue
                    try:
                        choice_int = int(choice)
                        if choice_int < 1 or choice_int > len(qualities):
                            print("잘못된 선택입니다.")
                            continue
                    except ValueError:
                        print("숫자를 입력하세요.")
                        continue
                    selected_quality = qualities[choice_int - 1]['id']
                    break

                while True:
                    output_folder = input("다운로드 받을 폴더 경로 (예: C:/Downloads): ").strip()
                    if not output_folder:
                        print("다운로드 경로를 입력하세요.")
                        continue
                    if not os.path.exists(output_folder):
                        try:
                            os.makedirs(output_folder)
                            print(f"폴더가 생성되었습니다: {output_folder}")
                        except Exception as e:
                            print("폴더 생성 실패:", e)
                            continue
                    break

                # HLS 분기: 구간 다운로드 불허용 → 전체 다운로드 진행
                if vod_info.get("inKey") is None:
                    print("\n빠른 다시보기(HLS) 다운로드는 구간 다운로드가 지원되지 않습니다. 전체 다운로드로 진행합니다.")
                    download_section = None
                else:
                    # DASH 분기: 사용자가 입력한 구간 형식을 그대로 사용
                    while True:
                        section_input = input("다운로드 구간 (00:00:00~00:00:00, 전체: Enter): ").strip()
                        if not section_input:
                            print("전체 다운로드로 진행합니다.")
                            download_section = None
                            break
                        match = re.match(r'^(\d{2}:\d{2}:\d{2})~(\d{2}:\d{2}:\d{2})$', section_input)
                        if not match:
                            print("입력 형식이 올바르지 않습니다. 다시 입력해주세요.")
                            continue
                        download_section = section_input
                        break

                if vod_status in ["UPLOAD", "NONE"]:
                    speed_option = "nolimit"
                    print("\n다운로드 속도 옵션: 제한없음(nolimit)")
                else:
                    print("\n다운로드 속도 옵션 선택:")
                    print("1. 100% (16분할)")
                    print("2. 75% (12분할)")
                    print("3. 50% (8분할)")
                    print("4. 25% (4분할)")
                    print("5. 분할 없음")
                    speed_mapping = {1: "100%", 2: "75%", 3: "50%", 4: "25%", 5: "분할 없음"}
                    while True:
                        speed_choice = input("옵션 번호: ").strip()
                        if not speed_choice:
                            print("값을 입력해야 합니다.")
                            continue
                        try:
                            sp = int(speed_choice)
                            if sp not in speed_mapping:
                                print("잘못된 선택입니다.")
                                continue
                            speed_option = speed_mapping[sp]
                            break
                        except ValueError:
                            print("숫자를 입력하세요.")
                            continue

                print("\n최종 정보 확인:")
                print("VOD URL:", vod_url)
                print("품질 ID:", selected_quality)
                print("폴더:", output_folder)
                print("파일명:", auto_filename)
                print("속도 옵션:", speed_option)
                print("구간:", download_section if download_section else "전체")
                confirm = input("다운로드를 시작하시겠습니까? (y 혹은 n 입력): ").strip().lower()
                print("[DEBUG] confirm 입력:", confirm)
                if confirm != "y":
                    print("취소되었습니다.")
                    input("계속하려면 Enter를 누르세요.")
                    continue

                try:
                    downloadVOD(vod_url, selected_quality, output_folder, auto_filename, speed_option, download_section)
                except Exception as e:
                    print("다운로드 중 오류 발생:", e)
                    input("계속하려면 Enter를 누르세요.")
                    continue

            run_again = input("\n다시 실행하시겠습니까? (y 혹은 n 입력): ").strip().lower()
            if run_again != "y":
                break
    input("\n프로그램을 종료하려면 Enter키를 누르세요.")

if __name__ == '__main__':
    main()
