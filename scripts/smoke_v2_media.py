"""Real FFmpeg/FFprobe v2 smoke, entirely inside a disposable directory.

Run: python scripts/smoke_v2_media.py
Requires ffmpeg and ffprobe on PATH. Does not use recordings or configuration.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from module.v2_repository import V2Repository
from module.v2_storage import StorageRoot
from module.v2_worker import V2Worker


def main() -> int:
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        print("FFmpeg and FFprobe are required for this smoke test.", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="v2-real-media-") as folder:
        root = Path(folder)
        media, archive = root / "media", root / "archive"
        media.mkdir()
        archive.mkdir()
        first, second = media / "first.ts", media / "second.ts"
        subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                        "testsrc=size=128x72:rate=10", "-t", "1", "-c:v", "mpeg2video",
                        "-f", "mpegts", "-n", str(first)], check=True)
        second.write_bytes(first.read_bytes())
        sources = (first, second)
        hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
        repo = V2Repository(root / "jobs.sqlite3")
        repo.initialize()
        repo.upsert_channel("channel")
        repo.upsert_broadcast("broadcast", "channel")
        for i, path in enumerate(sources):
            repo.upsert_artifact({"id": f"source-{i}", "broadcast_id": "broadcast", "kind": "original",
                "storage_id": "recordings", "relative_path": path.name, "size": path.stat().st_size})
        storages = {"recordings": StorageRoot("recordings", media), "archive": StorageRoot("archive", archive)}
        def worker():
            return V2Worker(repo, data_dir=root, storages=storages, ffmpeg=ffmpeg, ffprobe=ffprobe, poll_seconds=.02)
        active = worker()
        outcomes = []
        try:
            for kind in ("verify", "recover", "remux", "merge", "archive"):
                target = "broadcast" if kind == "merge" else "source-0"
                entity = repo.get_broadcast(target) if kind == "merge" else repo.get_artifact(target)
                job = repo.create_job(kind, target, input_revision=entity["revision"])
                active.run_once()
                state = repo.get_job(job["id"])
                if state["state"] != "succeeded":
                    raise AssertionError(state)
                outcomes.append({"kind": kind, "state": state["state"],
                                 "duration": state["result"].get("probe", {}).get("duration")})
            interrupted = repo.create_job("remux", "source-0", input_revision=repo.get_artifact("source-0")["revision"],
                                          options={"output_relative_path": "restart-result.ts"})
            with mock.patch.object(repo, "finish_job", side_effect=sqlite3.OperationalError("injected post-publication crash")):
                active.run_once()
            assert (media / "restart-result.ts").is_file()
            assert repo.get_job(interrupted["id"])["state"] == "running"
            active.release_instance_lock()
            active = worker()
            active.reconcile(startup=True)
            assert repo.get_job(interrupted["id"])["state"] == "succeeded"
            assert len(repo.get_attempts(interrupted["id"])) == 1
            assert hashes == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
            integrity = repo.integrity_check()
            assert integrity["ok"], integrity
            print(json.dumps({"jobs": outcomes, "restart_reconciliation": "succeeded_without_reexecution",
                              "original_hashes_unchanged": True, "database_integrity": integrity["integrity"],
                              "foreign_key_violations": integrity["foreign_keys"]}, indent=2))
        finally:
            active.release_instance_lock()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
