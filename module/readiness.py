"""Application readiness checks used by Docker and operators."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any


def _result(ok: bool, detail: str = "") -> dict[str, Any]:
    return {"ok": bool(ok), "detail": str(detail or "")[:500]}


def _probe_writable(path: Path) -> dict[str, Any]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".lar-ready-", dir=str(path))
        try:
            os.write(fd, b"ready")
        finally:
            os.close(fd)
        Path(name).unlink(missing_ok=True)
        return _result(True, str(path))
    except Exception as exc:
        return _result(False, f"{path}: {exc}")


def _probe_catalog() -> dict[str, Any]:
    try:
        from module import recording_catalog

        recording_catalog.init_catalog()
        with recording_catalog._LOCK, recording_catalog._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT 1").fetchone()
            conn.rollback()
        return _result(bool(row and int(row[0]) == 1), str(recording_catalog.DB_PATH))
    except Exception as exc:
        return _result(False, f"catalog: {exc}")


def _probe_tasks(started: bool, tasks: list[Any], *, expected: int, label: str) -> dict[str, Any]:
    live = sum(1 for task in tasks if task is not None and not task.done())
    done = sum(1 for task in tasks if task is not None and task.done())
    ok = bool(started and live >= expected and done == 0)
    return _result(ok, f"{label}: started={started}; live={live}; done={done}; expected={expected}")


def readiness_snapshot(operations: Any, platform: Any) -> dict[str, Any]:
    """Return a structured readiness snapshot without changing recorder state."""
    data_dir = Path(getattr(operations, "data_dir", Path.cwd()))
    recording_root = Path(getattr(operations, "recording_root", Path.cwd()))

    checks: dict[str, dict[str, Any]] = {
        "data_directory": _probe_writable(data_dir),
        "recording_directory": _probe_writable(recording_root),
        "catalog": _probe_catalog(),
        "operations_tasks": _probe_tasks(
            bool(getattr(operations, "_started", False)),
            list(getattr(operations, "background_tasks", []) or []),
            expected=2,
            label="operations",
        ),
        "platform_tasks": _probe_tasks(
            bool(getattr(platform, "_started", False)),
            list(getattr(platform, "tasks", []) or []),
            expected=2,
            label="platform",
        ),
    }

    try:
        storage = dict(operations.storage_info() or {})
        storage_ok = storage.get("status") != "error" and not bool(storage.get("recording_blocked"))
        checks["storage"] = _result(
            storage_ok,
            f"status={storage.get('status', 'unknown')}; free={storage.get('free_percent', 'unknown')}%",
        )
    except Exception as exc:
        checks["storage"] = _result(False, f"storage: {exc}")

    ready = all(item.get("ok") for item in checks.values())
    return {"status": "ready" if ready else "not_ready", "ready": ready, "checks": checks}
