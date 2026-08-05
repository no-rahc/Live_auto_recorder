"""
notifier.py — 통합 알림 모듈 (Telegram + Discord Webhook)

sendTelegram은 기존 data_manager에 유지하고,
이 모듈은 Discord 웹훅 전송 + 통합 notify() 래퍼를 제공한다.
"""
from __future__ import annotations
from module.log_setup import get_logger
logger = get_logger("notifier")

import json
import os
import time
import threading
from typing import Optional

import requests

from module.data_manager import loadConfig, loadTelegram, sendTelegram

# ── Discord rate-limit 보호 ──────────────────────────────────
_discord_lock = threading.Lock()
_discord_last_sent: float = 0.0
_DISCORD_MIN_INTERVAL = 1.0  # 초 (웹훅 레이트리밋 5req/2s 여유)


def _discord_webhook_url() -> Optional[str]:
    """config에서 Discord 웹훅 URL 읽기."""
    cfg = loadConfig()
    if not cfg.get("discord_enabled", False):
        return None
    url = (cfg.get("discord_webhook_url") or "").strip()
    return url if url.startswith("https://") else None


def sendDiscord(message: str, *, title: Optional[str] = None,
                color: int = 0x5865F2) -> bool:
    """
    Discord 웹훅으로 메시지 전송.
    성공 True / 실패·스킵 False.
    """
    global _discord_last_sent

    url = _discord_webhook_url()
    if not url:
        return False

    # 레이트리밋 보호
    with _discord_lock:
        now = time.monotonic()
        wait = _DISCORD_MIN_INTERVAL - (now - _discord_last_sent)
        if wait > 0:
            time.sleep(wait)
        _discord_last_sent = time.monotonic()

    # HTML 태그 → Discord 마크다운 변환
    text = message
    text = text.replace("<b>", "**").replace("</b>", "**")
    text = text.replace("<i>", "*").replace("</i>", "*")
    text = text.replace("<code>", "`").replace("</code>", "`")
    text = text.replace("<br>", "\n").replace("<br/>", "\n")

    payload: dict = {}
    if title:
        payload["embeds"] = [{
            "title": title,
            "description": text,
            "color": color,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            "footer": {"text": "Live Auto Recorder"},
        }]
    else:
        payload["content"] = text

    try:
        resp = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code in (200, 204):
            logger.info("Discord 알림 전송 성공.")
            return True
        else:
            logger.error(f"Discord 알림 실패: {resp.status_code} {resp.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"Discord 알림 전송 중 오류: {e}")
        return False


# ── 색상 프리셋 ──────────────────────────────────────────────
COLOR_REC_START  = 0xED4245   # 빨강 (녹화 시작)
COLOR_REC_STOP   = 0x57F287   # 초록 (녹화 종료)
COLOR_REC_ERROR  = 0xFEE75C   # 노랑 (경고/에러)
COLOR_REC_WATCH  = 0x5865F2   # 블루 (예약/대기)
COLOR_SYS_INFO   = 0x99AAB5   # 회색 (시스템)


def notify(message: str, *, title: Optional[str] = None,
           color: int = COLOR_SYS_INFO):
    """
    통합 알림: Telegram + Discord 동시 전송.
    기존 sendTelegram 호출을 이 함수로 대체하면 된다.
    """
    # Telegram (기존 로직 그대로)
    try:
        sendTelegram(message)
    except Exception as e:
        logger.warning(f"notify→telegram failed: {e}")

    # Discord
    try:
        sendDiscord(message, title=title, color=color)
    except Exception as e:
        logger.warning(f"notify→discord failed: {e}")
