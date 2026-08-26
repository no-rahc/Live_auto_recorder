"""Durable SQLite catalog for recording events and completed files."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

_DATA_DIR = Path(os.getenv("LAR_DATA_DIR", Path(__file__).resolve().parents[1] / "json"))
DB_PATH = _DATA_DIR / "recordings.sqlite3"
SCHEMA_VERSION = 4
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


def _migrate_v4(conn: sqlite3.Connection) -> None:
    columns = _columns(conn, "recordings")
    additions = {
        "broadcast_id": "TEXT NOT NULL DEFAULT ''",
        "segment_index": "INTEGER NOT NULL DEFAULT 1",
        "failure_code": "TEXT NOT NULL DEFAULT ''",
        "failure_detail": "TEXT NOT NULL DEFAULT ''",
        "failure_remedy": "TEXT NOT NULL DEFAULT ''",
    }
    for name, declaration in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE recordings ADD COLUMN {name} {declaration}")
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_recordings_broadcast ON recordings(broadcast_id, segment_index);
        CREATE TABLE IF NOT EXISTS broadcast_merges (
          broadcast_id TEXT PRIMARY KEY,
          status TEXT NOT NULL DEFAULT '',
          output_path TEXT NOT NULL DEFAULT '',
          error TEXT NOT NULL DEFAULT '',
          updated_epoch REAL NOT NULL DEFAULT 0
        );
        """
    )
    rows = conn.execute("SELECT id FROM recordings WHERE broadcast_id='' OR broadcast_id IS NULL").fetchall()
    for row in rows:
        conn.execute(
            "UPDATE recordings SET broadcast_id=?,segment_index=1 WHERE id=?",
            (f"legacy-{row['id']}", row["id"]),
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
            current = 3
        if current < 4:
            _migrate_v4(conn)
            conn.execute("PRAGMA user_version=4")
        conn.commit()


def _session_key(entry: dict[str, Any]) -> str:
    channel = str(entry.get("channel_id") or "")
    filename = str(entry.get("filename") or "")
    epoch = int(float(entry.get("epoch") or time.time()))
    return f"{channel}:{filename or epoch}"


def _broadcast_assignment(conn: sqlite3.Connection, entry: dict[str, Any], extra: dict[str, Any], epoch: float) -> tuple[str, int]:
    explicit = str(extra.get("broadcast_id") or "").strip()
    if explicit:
        row = conn.execute("SELECT COUNT(*) AS n FROM recordings WHERE broadcast_id=?", (explicit,)).fetchone()
        return explicit, int(row["n"] or 0) + 1
    channel_id = str(entry.get("channel_id") or "")
    title = str(extra.get("title") or extra.get("live_title") or "").strip()
    source_url = str(extra.get("source_url") or extra.get("url") or "").strip()
    gap = max(30, min(int(os.getenv("LAR_BROADCAST_GROUP_GAP_SECONDS", "900")), 7200))
    previous = conn.execute(
        "SELECT * FROM recordings WHERE channel_id=? AND ended_epoch>0 AND ?-ended_epoch BETWEEN 0 AND ? ORDER BY ended_epoch DESC LIMIT 1",
        (channel_id, epoch, gap),
    ).fetchone()
    if previous:
        previous_title = str(previous["title"] or "").strip()
        previous_url = str(previous["source_url"] or "").strip()
        # A channel URL is often stable across different live broadcasts. If both
        # sides have titles, require the title to match so two back-to-back shows
        # are never grouped just because they share the same channel URL.
        if title and previous_title:
            same_identity = title == previous_title
        elif source_url and previous_url:
            same_identity = source_url == previous_url
        else:
            same_identity = not title and not source_url
        if same_identity:
            broadcast_id = str(previous["broadcast_id"] or f"broadcast-{previous['id']}")
            if not previous["broadcast_id"]:
                conn.execute("UPDATE recordings SET broadcast_id=? WHERE id=?", (broadcast_id, previous["id"]))
            row = conn.execute("SELECT COUNT(*) AS n FROM recordings WHERE broadcast_id=?", (broadcast_id,)).fetchone()
            return broadcast_id, int(row["n"] or 0) + 1
    return f"broadcast-{uuid.uuid4().hex}", 1


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
            broadcast_id, segment_index = _broadcast_assignment(conn, entry, extra, epoch)
            conn.execute(
                """INSERT INTO recordings(session_key,channel_id,channel_name,platform,title,category,source_url,filename,file_path,started_at,started_epoch,status,reconnects,broadcast_id,segment_index,updated_epoch)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(session_key) DO UPDATE SET channel_name=excluded.channel_name, title=excluded.title, category=excluded.category, source_url=excluded.source_url, filename=excluded.filename, file_path=excluded.file_path, status='recording', stop_reason='', failure_code='', failure_detail='', failure_remedy='', updated_epoch=excluded.updated_epoch""",
                (
                    key, channel_id, str(entry.get("channel_name") or ""), str(entry.get("platform") or ""),
                    str(extra.get("title") or extra.get("live_title") or ""), str(extra.get("category") or ""),
                    str(extra.get("source_url") or extra.get("url") or ""), filename,
                    str(extra.get("file_path") or filename), str(entry.get("ts") or ""), epoch,
                    "recording", int(extra.get("restart_attempts") or 0), broadcast_id, segment_index, epoch,
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
                failure_code = failure_detail = failure_remedy = ""
                if event == "recording_failed":
                    try:
                        from module.failure_diagnostics import classify_failure
                        stderr = str(extra.get("process_stderr_tail") or "")
                        if not stderr:
                            try:
                                from module.recording_trace import trace_fields
                                stderr = str(trace_fields(channel_id, include_tail=True).get("process_stderr_tail") or "")
                            except Exception:
                                stderr = ""
                        diagnostic = classify_failure(
                            str(entry.get("error") or ""),
                            stderr,
                            platform=str(entry.get("platform") or ""),
                            exit_code=extra.get("process_exit_code"),
                        )
                        failure_code = diagnostic.get("code", "")
                        failure_detail = diagnostic.get("summary", "")
                        failure_remedy = diagnostic.get("remedy", "")
                    except Exception:
                        pass
                conn.execute(
                    "UPDATE recordings SET ended_at=?,ended_epoch=?,duration=?,status=?,error=?,failure_code=?,failure_detail=?,failure_remedy=?,filename=CASE WHEN ?<>'' THEN ? ELSE filename END,stop_reason=CASE WHEN ?<>'' THEN ? ELSE stop_reason END,updated_epoch=? WHERE id=?",
                    (str(entry.get("ts") or ""), epoch, str(entry.get("duration") or ""), status,
                     str(entry.get("error") or "")[:1000], failure_code, failure_detail, failure_remedy, filename, filename,
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


def list_broadcasts(*, limit: int = 100, offset: int = 0, channel_id: str = "", query: str = "") -> dict[str, Any]:
    """Return recording rows grouped into one logical live broadcast."""
    init_catalog()
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    where: list[str] = []
    args: list[Any] = []
    if channel_id:
        where.append("r.channel_id=?")
        args.append(channel_id)
    if query:
        where.append("(r.channel_name LIKE ? OR r.title LIKE ? OR r.filename LIKE ? OR r.error LIKE ?)")
        needle = f"%{query}%"
        args.extend([needle] * 4)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    base = " FROM recordings r" + clause
    with _LOCK, _connect() as conn:
        total = conn.execute("SELECT COUNT(DISTINCT r.broadcast_id)" + base, args).fetchone()[0]
        rows = conn.execute(
            """SELECT r.broadcast_id,
                      MAX(r.channel_id) AS channel_id, MAX(r.channel_name) AS channel_name,
                      MAX(r.platform) AS platform,
                      COALESCE(NULLIF(MAX(r.title),''), '') AS title,
                      MIN(r.started_at) AS started_at, MIN(r.started_epoch) AS started_epoch,
                      MAX(r.ended_at) AS ended_at, MAX(r.ended_epoch) AS ended_epoch,
                      COUNT(*) AS segment_count, SUM(r.file_size) AS file_size,
                      SUM(r.reconnects) AS reconnects,
                      SUM(CASE WHEN r.status='recording' THEN 1 ELSE 0 END) AS active_segments,
                      SUM(CASE WHEN r.status='failed' THEN 1 ELSE 0 END) AS failed_segments,
                      MAX(r.failure_code) AS failure_code, MAX(r.failure_detail) AS failure_detail,
                      MAX(r.failure_remedy) AS failure_remedy,
                      COALESCE(m.status,'') AS merge_status,
                      COALESCE(m.output_path,'') AS merged_path,
                      COALESCE(m.error,'') AS merge_error
                 FROM recordings r
            LEFT JOIN broadcast_merges m ON m.broadcast_id=r.broadcast_id"""
            + clause
            + " GROUP BY r.broadcast_id ORDER BY MIN(r.started_epoch) DESC LIMIT ? OFFSET ?",
            [*args, limit, offset],
        ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        segments = int(item.get("segment_count") or 0)
        active = int(item.pop("active_segments", 0) or 0)
        failed = int(item.pop("failed_segments", 0) or 0)
        item["status"] = "recording" if active else ("failed" if failed == segments and segments else "completed")
        items.append(item)
    return {"total": int(total or 0), "items": items, "limit": limit, "offset": offset}


def get_broadcast(broadcast_id: str) -> dict[str, Any] | None:
    init_catalog()
    bid = str(broadcast_id or "")
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM recordings WHERE broadcast_id=? ORDER BY segment_index,started_epoch,id",
            (bid,),
        ).fetchall()
        if not rows:
            return None
        merge = conn.execute("SELECT * FROM broadcast_merges WHERE broadcast_id=?", (bid,)).fetchone()
    segments = [dict(row) for row in rows]
    first = segments[0]
    return {
        "broadcast_id": bid,
        "channel_id": first.get("channel_id", ""),
        "channel_name": first.get("channel_name", ""),
        "platform": first.get("platform", ""),
        "title": first.get("title", ""),
        "started_at": first.get("started_at", ""),
        "started_epoch": min(float(item.get("started_epoch") or 0) for item in segments),
        "ended_at": segments[-1].get("ended_at", ""),
        "ended_epoch": max(float(item.get("ended_epoch") or 0) for item in segments),
        "segment_count": len(segments),
        "file_size": sum(int(item.get("file_size") or 0) for item in segments),
        "reconnects": sum(int(item.get("reconnects") or 0) for item in segments),
        "status": "recording" if any(item.get("status") == "recording" for item in segments) else ("failed" if all(item.get("status") == "failed" for item in segments) else "completed"),
        "merge": dict(merge) if merge else {"broadcast_id": bid, "status": "", "output_path": "", "error": ""},
        "segments": segments,
    }


def set_broadcast_merge(broadcast_id: str, *, status: str, output_path: str = "", error: str = "") -> None:
    init_catalog()
    now = time.time()
    with _LOCK, _connect() as conn:
        conn.execute(
            """INSERT INTO broadcast_merges(broadcast_id,status,output_path,error,updated_epoch)
               VALUES(?,?,?,?,?)
               ON CONFLICT(broadcast_id) DO UPDATE SET status=excluded.status,output_path=excluded.output_path,error=excluded.error,updated_epoch=excluded.updated_epoch""",
            (str(broadcast_id), str(status)[:40], str(output_path), str(error)[:1000], now),
        )


def list_merge_candidates(*, quiet_seconds: int = 900, limit: int = 10) -> list[str]:
    """Return completed multi-segment broadcasts old enough to be safe to merge."""
    init_catalog()
    cutoff = time.time() - max(30, int(quiet_seconds))
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            """SELECT r.broadcast_id
                 FROM recordings r
            LEFT JOIN broadcast_merges m ON m.broadcast_id=r.broadcast_id
             GROUP BY r.broadcast_id
               HAVING COUNT(*)>1
                  AND SUM(CASE WHEN r.status='recording' THEN 1 ELSE 0 END)=0
                  AND MAX(r.ended_epoch)>0 AND MAX(r.ended_epoch)<=?
                  AND COALESCE(MAX(m.status),'') NOT IN ('merging','completed')
             ORDER BY MAX(r.ended_epoch) ASC LIMIT ?""",
            (cutoff, max(1, min(int(limit), 50))),
        ).fetchall()
    return [str(row["broadcast_id"]) for row in rows]


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
