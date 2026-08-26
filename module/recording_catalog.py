"""Durable SQLite catalog for recording events and completed files."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_DATA_DIR = Path(os.getenv("LAR_DATA_DIR", Path(__file__).resolve().parents[1] / "json"))
DB_PATH = _DATA_DIR / "recordings.sqlite3"
SCHEMA_VERSION = 3
_LOCK = threading.RLock()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _backup_before_migration(conn: sqlite3.Connection, current: int, existed_before: bool) -> Path | None:
    if current >= SCHEMA_VERSION or not existed_before:
        return None
    backup = DB_PATH.with_name(
        f"{DB_PATH.name}.pre-migrate-v{current}-to-v{SCHEMA_VERSION}-{int(time.time())}.bak"
    )
    dest = sqlite3.connect(backup)
    try:
        conn.backup(dest)
    finally:
        dest.close()
    return backup


def _migrate_v1(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          epoch REAL NOT NULL,
          ts TEXT NOT NULL,
          channel_id TEXT NOT NULL DEFAULT '',
          channel_name TEXT NOT NULL DEFAULT '',
          platform TEXT NOT NULL DEFAULT '',
          event TEXT NOT NULL,
          filename TEXT NOT NULL DEFAULT '',
          duration TEXT NOT NULL DEFAULT '',
          error TEXT NOT NULL DEFAULT '',
          extra_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_events_epoch ON events(epoch DESC);
        CREATE INDEX IF NOT EXISTS idx_events_channel ON events(channel_id, epoch DESC);
        CREATE INDEX IF NOT EXISTS idx_events_event ON events(event, epoch DESC);

        CREATE TABLE IF NOT EXISTS recordings (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session_key TEXT NOT NULL UNIQUE,
          channel_id TEXT NOT NULL DEFAULT '',
          channel_name TEXT NOT NULL DEFAULT '',
          platform TEXT NOT NULL DEFAULT '',
          title TEXT NOT NULL DEFAULT '',
          category TEXT NOT NULL DEFAULT '',
          source_url TEXT NOT NULL DEFAULT '',
          filename TEXT NOT NULL DEFAULT '',
          file_path TEXT NOT NULL DEFAULT '',
          file_size INTEGER NOT NULL DEFAULT 0,
          started_at TEXT NOT NULL DEFAULT '',
          started_epoch REAL NOT NULL DEFAULT 0,
          ended_at TEXT NOT NULL DEFAULT '',
          ended_epoch REAL NOT NULL DEFAULT 0,
          duration TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'recording',
          error TEXT NOT NULL DEFAULT '',
          reconnects INTEGER NOT NULL DEFAULT 0,
          postprocess_status TEXT NOT NULL DEFAULT '',
          validation_status TEXT NOT NULL DEFAULT '',
          validation_detail TEXT NOT NULL DEFAULT '',
          archive_status TEXT NOT NULL DEFAULT '',
          archive_target TEXT NOT NULL DEFAULT '',
          updated_epoch REAL NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_recordings_started ON recordings(started_epoch DESC);
        CREATE INDEX IF NOT EXISTS idx_recordings_channel ON recordings(channel_id, started_epoch DESC);
        CREATE INDEX IF NOT EXISTS idx_recordings_status ON recordings(status, started_epoch DESC);

        CREATE TABLE IF NOT EXISTS notification_queue (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          event_type TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'queued',
          attempts INTEGER NOT NULL DEFAULT 0,
          next_attempt REAL NOT NULL DEFAULT 0,
          last_error TEXT NOT NULL DEFAULT '',
          created_epoch REAL NOT NULL,
          sent_epoch REAL NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_notification_queue ON notification_queue(status, next_attempt);

        CREATE TABLE IF NOT EXISTS api_tokens (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          token_hash TEXT NOT NULL UNIQUE,
          token_prefix TEXT NOT NULL,
          scopes TEXT NOT NULL,
          created_epoch REAL NOT NULL,
          expires_epoch REAL NOT NULL DEFAULT 0,
          last_used_epoch REAL NOT NULL DEFAULT 0,
          revoked INTEGER NOT NULL DEFAULT 0
        );
        """
    )


def _migrate_v2(conn: sqlite3.Connection) -> None:
    if "delivery_json" not in _columns(conn, "notification_queue"):
        conn.execute("ALTER TABLE notification_queue ADD COLUMN delivery_json TEXT NOT NULL DEFAULT '{}'")
    if "stop_reason" not in _columns(conn, "recordings"):
        conn.execute("ALTER TABLE recordings ADD COLUMN stop_reason TEXT NOT NULL DEFAULT ''")


def _migrate_v3(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS archive_jobs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          recording_id INTEGER NOT NULL,
          status TEXT NOT NULL DEFAULT 'queued',
          attempts INTEGER NOT NULL DEFAULT 0,
          next_attempt REAL NOT NULL DEFAULT 0,
          target TEXT NOT NULL DEFAULT '',
          last_error TEXT NOT NULL DEFAULT '',
          created_epoch REAL NOT NULL,
          updated_epoch REAL NOT NULL,
          FOREIGN KEY(recording_id) REFERENCES recordings(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_archive_jobs_queue ON archive_jobs(status, next_attempt, id);
        CREATE INDEX IF NOT EXISTS idx_archive_jobs_recording ON archive_jobs(recording_id, id DESC);
        """
    )


def init_catalog() -> None:
    existed_before = DB_PATH.exists() and DB_PATH.stat().st_size > 0
    with _LOCK, _connect() as conn:
        current = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if current < SCHEMA_VERSION:
            _backup_before_migration(conn, current, existed_before)
        if current < 1:
            _migrate_v1(conn)
            conn.execute("PRAGMA user_version=1")
            current = 1
        if current < 2:
            _migrate_v2(conn)
            conn.execute("PRAGMA user_version=2")
            current = 2
        if current < 3:
            _migrate_v3(conn)
            conn.execute("PRAGMA user_version=3")
        conn.commit()


def _session_key(entry: dict[str, Any]) -> str:
    channel = str(entry.get("channel_id") or "")
    filename = str(entry.get("filename") or "")
    epoch = int(float(entry.get("epoch") or time.time()))
    return f"{channel}:{filename or epoch}"


def record_event(entry: dict[str, Any]) -> None:
    """Persist one legacy recording-history event and update its session row."""
    init_catalog()
    extra = {k: v for k, v in entry.items() if k not in {
        "epoch", "ts", "channel_id", "channel_name", "platform", "event", "filename", "duration", "error"
    }}
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO events(epoch,ts,channel_id,channel_name,platform,event,filename,duration,error,extra_json) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                float(entry.get("epoch") or time.time()), str(entry.get("ts") or ""),
                str(entry.get("channel_id") or ""), str(entry.get("channel_name") or ""),
                str(entry.get("platform") or ""), str(entry.get("event") or ""),
                str(entry.get("filename") or ""), str(entry.get("duration") or ""),
                str(entry.get("error") or "")[:1000], json.dumps(extra, ensure_ascii=False),
            ),
        )
        event = str(entry.get("event") or "")
        channel_id = str(entry.get("channel_id") or "")
        filename = str(entry.get("filename") or "")
        epoch = float(entry.get("epoch") or time.time())
        if event == "recording_started":
            key = _session_key(entry)
            conn.execute(
                """INSERT INTO recordings(session_key,channel_id,channel_name,platform,title,category,source_url,filename,file_path,started_at,started_epoch,status,reconnects,updated_epoch)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(session_key) DO UPDATE SET channel_name=excluded.channel_name, title=excluded.title, category=excluded.category, source_url=excluded.source_url, filename=excluded.filename, file_path=excluded.file_path, status='recording', stop_reason='', updated_epoch=excluded.updated_epoch""",
                (
                    key, channel_id, str(entry.get("channel_name") or ""), str(entry.get("platform") or ""),
                    str(extra.get("title") or extra.get("live_title") or ""), str(extra.get("category") or ""),
                    str(extra.get("source_url") or extra.get("url") or ""), filename,
                    str(extra.get("file_path") or filename), str(entry.get("ts") or ""), epoch,
                    "recording", int(extra.get("restart_attempts") or 0), epoch,
                ),
            )
        elif event in {"recording_stopped", "recording_failed"}:
            row = conn.execute(
                "SELECT id FROM recordings WHERE channel_id=? AND (filename=? OR ?='') ORDER BY started_epoch DESC LIMIT 1",
                (channel_id, filename, filename),
            ).fetchone()
            status = "completed" if event == "recording_stopped" else "failed"
            stop_reason = str(extra.get("stop_reason") or "")
            if row:
                conn.execute(
                    "UPDATE recordings SET ended_at=?,ended_epoch=?,duration=?,status=?,error=?,filename=CASE WHEN ?<>'' THEN ? ELSE filename END,stop_reason=CASE WHEN ?<>'' THEN ? ELSE stop_reason END,updated_epoch=? WHERE id=?",
                    (str(entry.get("ts") or ""), epoch, str(entry.get("duration") or ""), status,
                     str(entry.get("error") or "")[:1000], filename, filename,
                     stop_reason, stop_reason, epoch, row["id"]),
                )
        elif event in {"postprocess_done", "postprocess_failed"}:
            row = conn.execute(
                "SELECT id FROM recordings WHERE channel_id=? ORDER BY started_epoch DESC LIMIT 1", (channel_id,)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE recordings SET postprocess_status=?,updated_epoch=? WHERE id=?",
                    ("completed" if event == "postprocess_done" else "failed", epoch, row["id"]),
                )


def migrate_jsonl(path: str | Path) -> int:
    """Import legacy JSONL events once; duplicate event tuples are skipped."""
    source = Path(path)
    if not source.exists():
        return 0
    init_catalog()
    imported = 0
    with _LOCK, _connect() as conn:
        existing = conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
    if existing:
        return 0
    for line in source.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict) and item.get("event"):
            record_event(item)
            imported += 1
    return imported


def list_events(*, limit: int = 50, channel_id: str = "", event: str = "") -> list[dict[str, Any]]:
    """Read recording lifecycle events from the durable catalog."""
    init_catalog()
    limit = max(1, min(int(limit), 10000))
    where: list[str] = []
    args: list[Any] = []
    if channel_id:
        where.append("channel_id=?")
        args.append(str(channel_id))
    if event:
        where.append("event=?")
        args.append(str(event))
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT epoch,ts,channel_id,channel_name,platform,event,filename,duration,error,extra_json "
            "FROM events" + clause + " ORDER BY epoch DESC LIMIT ?",
            [*args, limit],
        ).fetchall()

    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        raw_extra = item.pop("extra_json", "{}")
        try:
            extra = json.loads(raw_extra or "{}")
        except Exception:
            extra = {}
        if isinstance(extra, dict):
            item.update(extra)
        items.append(item)
    return items


def list_recordings(*, limit: int = 100, offset: int = 0, channel_id: str = "", status: str = "", query: str = "") -> dict[str, Any]:
    init_catalog()
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    where: list[str] = []
    args: list[Any] = []
    if channel_id:
        where.append("channel_id=?")
        args.append(channel_id)
    if status:
        where.append("status=?")
        args.append(status)
    if query:
        where.append("(channel_name LIKE ? OR title LIKE ? OR filename LIKE ? OR error LIKE ?)")
        needle = f"%{query}%"
        args.extend([needle] * 4)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    with _LOCK, _connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM recordings" + clause, args).fetchone()["n"]
        rows = conn.execute(
            "SELECT * FROM recordings" + clause + " ORDER BY started_epoch DESC LIMIT ? OFFSET ?",
            [*args, limit, offset],
        ).fetchall()
    return {"total": total, "items": [dict(row) for row in rows], "limit": limit, "offset": offset}


def get_recording(recording_id: int) -> dict[str, Any] | None:
    init_catalog()
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT * FROM recordings WHERE id=?", (int(recording_id),)).fetchone()
    return dict(row) if row else None


def update_recording(recording_id: int, **fields: Any) -> None:
    allowed = {"file_path", "file_size", "validation_status", "validation_detail", "archive_status", "archive_target", "postprocess_status", "error", "stop_reason"}
    pairs = [(key, value) for key, value in fields.items() if key in allowed]
    if not pairs:
        return
    pairs.append(("updated_epoch", time.time()))
    sql = ",".join(f"{key}=?" for key, _ in pairs)
    with _LOCK, _connect() as conn:
        conn.execute(f"UPDATE recordings SET {sql} WHERE id=?", [*[value for _, value in pairs], int(recording_id)])


def set_active_stop_reason(channel_id: str, reason: str) -> bool:
    """Attach a control stop reason to the active recording, if one exists."""
    init_catalog()
    with _LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT id FROM recordings WHERE channel_id=? AND status='recording' ORDER BY started_epoch DESC LIMIT 1",
            (str(channel_id),),
        ).fetchone()
        if not row:
            return False
        conn.execute(
            "UPDATE recordings SET stop_reason=?,updated_epoch=? WHERE id=?",
            (str(reason)[:80], time.time(), row["id"]),
        )
    return True


def find_latest_recording(channel_id: str, filename: str = "") -> dict[str, Any] | None:
    init_catalog()
    with _LOCK, _connect() as conn:
        if filename:
            row = conn.execute("SELECT * FROM recordings WHERE channel_id=? AND filename=? ORDER BY started_epoch DESC LIMIT 1", (channel_id, filename)).fetchone()
        else:
            row = conn.execute("SELECT * FROM recordings WHERE channel_id=? ORDER BY started_epoch DESC LIMIT 1", (channel_id,)).fetchone()
    return dict(row) if row else None
