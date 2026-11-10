#!/usr/bin/env python3
"""Read-only safety preflight for the opt-in durable recorder on the host.

Does not initialize SQLite, create a mount marker, or start a recorder.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from module.v2_storage import StorageRoot, preflight_database_location, preflight_storage


def evaluate(
    data_dir: str | Path,
    recordings_root: str | Path,
    marker: str = ".lar-storage-id",
    expected_marker: str | None = None,
) -> dict:
    """Report existing storage readiness without making any mutations."""
    data = preflight_database_location(Path(data_dir), min_free_bytes=16 * 1024 * 1024)
    recordings = preflight_storage(
        StorageRoot(
            storage_id="recordings",
            root=Path(recordings_root),
            marker=marker,
            expected_marker=expected_marker,
            min_free_bytes=64 * 1024 * 1024,
        ),
        probe_writes=False,
    )
    return {
        "ready": bool(data["ok"] and recordings["ok"]),
        "read_only": True,
        "data": data,
        "recordings": recordings,
        "manual_release_gates_required": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=os.getenv("LAR_DATA_DIR") or "data")
    parser.add_argument("--recordings-root", default=os.getenv("RECORDINGS_ROOT") or "recordings")
    parser.add_argument("--marker", default=os.getenv("LAR_V2_RECORDINGS_MARKER") or ".lar-storage-id")
    parser.add_argument("--expected-marker", default=os.getenv("LAR_V2_RECORDINGS_MARKER_VALUE") or None)
    args = parser.parse_args(argv)
    report = evaluate(args.data_dir, args.recordings_root, args.marker, args.expected_marker)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
