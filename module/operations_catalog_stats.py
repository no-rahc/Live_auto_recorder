"""Operations statistics backed by the durable SQLite recording catalog."""
from __future__ import annotations

import csv
import io
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from module.operations_common import _bytes_human, _duration_seconds
from module.recording_catalog import _LOCK as DB_LOCK, _connect, init_catalog


class CatalogStatsMixin:
    def statistics(self) -> dict[str, Any]:
        init_catalog()
        with DB_LOCK, _connect() as conn:
            rows = [dict(row) for row in conn.execute("SELECT * FROM recordings ORDER BY started_epoch DESC").fetchall()]
        today = datetime.now().date()
        daily: list[dict[str, Any]] = []
        for offset in range(13, -1, -1):
            day = today - timedelta(days=offset)
            key = day.isoformat()
            day_rows = [item for item in rows if str(item.get("started_at") or "").startswith(key)]
            daily.append({
                "date": key,
                "recordings": len(day_rows),
                "failures": sum(item.get("status") == "failed" for item in day_rows),
                "duration_seconds": sum(_duration_seconds(str(item.get("duration") or "")) for item in day_rows),
            })
        by_channel: dict[str, dict[str, Any]] = {}
        for item in rows:
            name = str(item.get("channel_name") or item.get("channel_id") or "알 수 없음")
            bucket = by_channel.setdefault(name, {"channel": name, "recordings": 0, "failures": 0, "duration_seconds": 0, "storage_bytes": 0})
            bucket["recordings"] += 1
            bucket["failures"] += int(item.get("status") == "failed")
            bucket["duration_seconds"] += _duration_seconds(str(item.get("duration") or ""))
            bucket["storage_bytes"] += int(item.get("file_size") or 0)
        failures = Counter(str(item.get("error") or "원인 미기록")[:120] for item in rows if item.get("status") == "failed")
        starts = len(rows)
        failed = sum(item.get("status") == "failed" for item in rows)
        return {
            "total_recordings": starts,
            "total_failures": failed,
            "success_rate": round((max(0, starts - failed) / starts * 100), 1) if starts else 100.0,
            "total_duration_seconds": sum(_duration_seconds(str(item.get("duration") or "")) for item in rows),
            "daily": daily,
            "by_channel": [
                {**item, "storage_text": _bytes_human(item.get("storage_bytes", 0))}
                for item in sorted(by_channel.values(), key=lambda item: item["recordings"], reverse=True)
            ],
            "failure_reasons": [{"reason": reason, "count": count} for reason, count in failures.most_common(10)],
        }

    def statistics_csv(self) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["date", "recordings", "failures", "duration_seconds"])
        for row in self.statistics()["daily"]:
            writer.writerow([row["date"], row["recordings"], row["failures"], row["duration_seconds"]])
        return output.getvalue()
