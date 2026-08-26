"""Classify recorder failures into stable, operator-friendly causes."""
from __future__ import annotations

import re
from typing import Any


_RULES: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    (
        "auth",
        "인증/쿠키 문제",
        ("401", "403", "unauthorized", "forbidden", "sign in", "login required", "cookie", "cookies", "nid_aut", "nid_ses"),
        "플랫폼 쿠키를 다시 등록하고 로그인/연령 제한 방송 접근 여부를 확인하세요.",
    ),
    (
        "rate_limit",
        "요청 제한",
        ("429", "too many requests", "rate limit", "ratelimit"),
        "잠시 후 다시 시도하고 재확인 주기를 너무 짧게 설정하지 않았는지 확인하세요.",
    ),
    (
        "network",
        "네트워크 연결 문제",
        (
            "timed out", "timeout", "connection reset", "connection refused", "connection aborted",
            "temporary failure", "name or service not known", "nodename nor servname", "dns",
            "network is unreachable", "remote end closed", "server disconnected",
        ),
        "인터넷 연결, DNS, 방화벽, 프록시/VPN 상태를 확인하세요.",
    ),
    (
        "disk_full",
        "저장 공간 부족",
        ("no space left on device", "enospc", "disk full", "not enough space"),
        "녹화 저장소 여유 공간을 확보한 뒤 다시 시작하세요.",
    ),
    (
        "permission",
        "파일 권한 문제",
        ("permission denied", "eacces", "operation not permitted", "read-only file system"),
        "녹화 폴더와 마운트의 UID/GID 및 쓰기 권한을 확인하세요.",
    ),
    (
        "tool_missing",
        "필수 도구 누락",
        ("command not found", "no such file or directory", "not recognized as an internal", "executable file not found"),
        "FFmpeg, Streamlink, ytarchive 설치와 PATH를 확인하세요.",
    ),
    (
        "stream_unavailable",
        "스트림을 재생할 수 없음",
        (
            "no playable streams", "no streams found", "stream unavailable", "private video", "video unavailable",
            "this live event has ended", "live event will begin", "offline", "not live", "premiere will begin",
        ),
        "방송이 실제 라이브인지, 비공개/구독/지역 제한이 없는지 확인하세요.",
    ),
    (
        "media_error",
        "미디어/컨테이너 오류",
        ("invalid data found", "moov atom not found", "non-monotonous dts", "error muxing", "muxer", "decoder", "encoder"),
        "완료 파일 검증·복구를 실행하고 FFmpeg 로그를 확인하세요.",
    ),
)


def classify_failure(
    error: str = "",
    stderr: str = "",
    *,
    platform: str = "",
    exit_code: Any = None,
) -> dict[str, str]:
    """Return a stable classification without exposing raw secrets."""
    text = "\n".join(part for part in (str(error or ""), str(stderr or "")) if part).lower()
    for code, label, needles, remedy in _RULES:
        if any(needle in text for needle in needles):
            return {
                "code": code,
                "label": label,
                "summary": _summary(error, stderr, label, exit_code),
                "remedy": remedy,
            }
    if exit_code not in (None, 0, "0", ""):
        return {
            "code": "process_exit",
            "label": "녹화 프로세스 비정상 종료",
            "summary": _summary(error, stderr, "녹화 프로세스가 비정상 종료되었습니다.", exit_code),
            "remedy": "운영 관리의 녹화 상세에서 프로세스 로그를 확인하고 필요하면 수동 복구를 실행하세요.",
        }
    return {
        "code": "unknown",
        "label": "원인 미분류",
        "summary": _summary(error, stderr, "자동으로 원인을 분류하지 못했습니다.", exit_code),
        "remedy": "녹화 상세의 stderr와 작업 기록을 확인하세요.",
    }


def _summary(error: str, stderr: str, fallback: str, exit_code: Any) -> str:
    source = str(error or "").strip()
    if not source:
        lines = [line.strip() for line in str(stderr or "").splitlines() if line.strip()]
        source = lines[-1] if lines else fallback
    source = re.sub(r"(?i)(authorization\s*:\s*)\S+", r"\1***", source)
    source = re.sub(r"(?i)(nid_(?:aut|ses)=)[^;\s]+", r"\1***", source)
    source = source[:350]
    if exit_code not in (None, ""):
        source = f"exit={exit_code} · {source}"
    return source
