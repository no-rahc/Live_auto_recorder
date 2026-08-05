import os
import time
import sys
import subprocess

def install_and_check_requests():
    module_name = "requests"

    # 모듈 설치 여부 확인
    try:
        __import__(module_name) 
        print(f"'{module_name}' 모듈이 이미 설치되어 있습니다.")
    except ImportError:
        print(f"'{module_name}' 모듈이 설치되지 않았습니다. 설치를 진행합니다...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", module_name])
            print(f"'{module_name}' 모듈 설치 완료.")

            # 설치 후 다시 확인
            try:
                __import__(module_name)
                print(f"'{module_name}' 모듈이 정상적으로 설치되었습니다.")
            except ImportError:
                print(f"'{module_name}' 모듈이 설치되었으나, 정상적으로 불러올 수 없습니다.")
        except subprocess.CalledProcessError as e:
            print(f"모듈 설치 중 오류 발생: {e}")

install_and_check_requests()

import requests
import zipfile
import shutil


def download_file(url, dest_path):
    print(f"다운로드 시작: {url}")
    r = requests.get(url, stream=True)
    if r.status_code == 200:
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        print(f"다운로드 완료: {dest_path}\n")
    else:
        raise Exception(f"다운로드 실패: HTTP {r.status_code}")


def extract_and_rename(zip_path, dependent_dir, desired_name):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    temp_extract_dir = os.path.join(base_dir, "temp_extract")
    if not os.path.exists(temp_extract_dir):
        os.makedirs(temp_extract_dir)

    print(f"압축 해제 중: {zip_path} -> {temp_extract_dir}")
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(path=temp_extract_dir)
        namelist = z.namelist()

    top_dirs = [name.split("/")[0] for name in namelist if name.strip()]
    top_dirs = list(set(top_dirs))
    if not top_dirs:
        raise Exception("압축 해제한 파일에서 최상위 폴더를 찾을 수 없습니다.")
    extracted_folder = os.path.join(temp_extract_dir, top_dirs[0])

    final_path = os.path.join(dependent_dir, desired_name)
    if os.path.exists(final_path):
        shutil.rmtree(final_path)
    shutil.move(extracted_folder, final_path)
    print(f"압축 해제 및 폴더명 변경 완료: {final_path}")

    shutil.rmtree(temp_extract_dir)


def ensure_directory(path):
    if not os.path.exists(path):
        os.makedirs(path)
        print(f"디렉토리 생성: {path}")
    else:
        print(f"디렉토리 존재: {path}")


def main():
    install_and_check_requests()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    dependent_dir = os.path.join(base_dir, "dependent")
    ensure_directory(dependent_dir)

    downloads = {
        "ffmpeg": {
            "url": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
            "desired_name": "ffmpeg"
        },
        "streamlink": {
            "url": "https://github.com/streamlink/windows-builds/releases/download/7.5.0-1/streamlink-7.5.0-1-py313-x86_64.zip",
            "desired_name": "streamlink"
        },
        "aria2c": {
            "url": "https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0-win-64bit-build1.zip",
            "desired_name": "aria2c"
        },
        "yt-dlp": {
            "url": "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe",
            "desired_name": "yt-dlp"
        },
        "ytarchive": {
            "url": "https://github.com/Kethsar/ytarchive/releases/download/v0.5.0/ytarchive_windows_amd64.zip",
            "desired_name": "ytarchive"
        }
    }

    for tool, info in downloads.items():
        print(f"==== {tool} 설치 시작 ====")

        if tool == "yt-dlp":
            tmp_exe = os.path.join(base_dir, "yt-dlp.exe")
            try:
                download_file(info["url"], tmp_exe)

                final_dir = os.path.join(dependent_dir, info["desired_name"])
                ensure_directory(final_dir)
                final_exe = os.path.join(final_dir, "yt-dlp.exe")

                if os.path.exists(final_exe):
                    os.remove(final_exe)
                shutil.move(tmp_exe, final_exe)
                print(f"yt-dlp 이동 완료 → {final_exe}")

            except Exception as e:
                print(f"{tool} 설치 중 오류: {e}")
            finally:

                if os.path.exists(tmp_exe):
                    try:
                        os.remove(tmp_exe)
                    except Exception as e:
                        print(f"yt-dlp 임시 파일 삭제 오류: {e}")

        elif tool == "ytarchive":
            tmp_zip = os.path.join(base_dir, "ytarchive.zip")
            try:
                download_file(info["url"], tmp_zip)

                temp_dir = os.path.join(base_dir, "temp_extract")
                ensure_directory(temp_dir)
                with zipfile.ZipFile(tmp_zip, "r") as zf:
                    zf.extractall(temp_dir)

                exe_path = None
                for root, _, files in os.walk(temp_dir):
                    for f in files:
                        if f.lower() == "ytarchive.exe":
                            exe_path = os.path.join(root, f)
                            break
                    if exe_path:
                        break
                if not exe_path:
                    raise Exception("ytarchive.exe 를 찾을 수 없습니다.")

                final_dir = os.path.join(dependent_dir, info["desired_name"])
                ensure_directory(final_dir)
                final_exe = os.path.join(final_dir, "ytarchive.exe")

                if os.path.exists(final_exe):
                    os.remove(final_exe)
                shutil.move(exe_path, final_exe)
                print(f"ytarchive 이동 완료 → {final_exe}")

            except Exception as e:
                print(f"{tool} 설치 중 오류: {e}")
            finally:
                if os.path.exists(tmp_zip):
                    os.remove(tmp_zip)
                temp_dir = os.path.join(base_dir, "temp_extract")
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)

        else:
            tmp_zip = os.path.join(base_dir, f"{tool}.zip")
            try:
                download_file(info["url"], tmp_zip)
                extract_and_rename(tmp_zip, dependent_dir, info["desired_name"])
            except Exception as e:
                print(f"{tool} 설치 중 오류: {e}")
            finally:
                if os.path.exists(tmp_zip):
                    os.remove(tmp_zip)

        print(f"==== {tool} 설치 완료 ====\n")

    # streamlink 패키지 내부 중복 ffmpeg 제거
    streamlink_ffmpeg = os.path.join(dependent_dir, "streamlink", "ffmpeg")
    if os.path.exists(streamlink_ffmpeg):
        shutil.rmtree(streamlink_ffmpeg)
        print(f"중복된 ffmpeg 폴더 삭제 완료: {streamlink_ffmpeg}")


if __name__ == "__main__":
    main()
