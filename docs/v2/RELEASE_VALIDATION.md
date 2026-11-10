# V2 real-device release validation (not yet completed)

This is a **required manual release gate**, not a claim that CI reproduced NAS, provider
accounts, or physical ARM64 devices. Keep `LAR_V2_ENABLED=false` until all gates
have evidence for the exact image digest under review.

## Before testing (no live data destruction)

1. Use an isolated recorder instance and noncritical CHZZK/YouTube accounts.
   Record the Git commit SHA, Docker image digest, OS, CPU architecture, disk
   filesystem, NAS model, and network type. Keep any cookies and access tokens
   out of logs, screenshots, and Git.
2. Take an offline copy of `data/` and representative recordings. Verify the
   backup checksum and restore a copy to a disposable directory; do not test
   destructive recovery against the only real recording archive.
3. Create the media identity marker on the **intended mounted volume**, never on
   a missing-mount fallback. Set `LAR_V2_RECORDINGS_MARKER_VALUE` to its known
   value. Ensure SQLite metadata lives on host-local storage, not SMB/NFS.
4. Run the read-only preflight from the repository root:
   `python scripts/check_v2_readiness.py --data-dir ./data --recordings-root /path/to/mounted/recordings --expected-marker YOUR_MARKER`
   Exit code 0 means basic path/mount conditions are met, **not** that the
   recorder is safe to release. This command never writes/creates test data.

## Required scenarios

| Gate | Scenario | Pass condition and evidence |
|---|---|---|
| Real providers | CHZZK and YouTube start/stop/reconnect/verify/merge on both amd64 and arm64 | Correct file lengths, verified media, no original loss, anonymized logs |
| NAS 24-hour soak | Continuous capture plus background verification and merge | Record CPU, RSS, disk I/O, SQLite WAL growth, queue delays and disk free space hourly; no unbounded growth |
| Missing mount | Disconnect and restore a **test** mount before launch and during capture | Missing marker blocks writes; no local fallback recordings; originals on NAS remain intact |
| Disk full | Fill only a disposable quota-bound test volume | New capture/jobs block cleanly; existing recordings unchanged; recovery after space returns |
| Abrupt process/container kill | SIGKILL before/during media output and database/publication boundaries | Fail closed, stale attempt fenced, no second publication or overwrites; manual reconciliation verified |
| Backup/restore | Stop service, restore representative v1/v2 data in isolation, restart | SQLite integrity check, channel state and recording paths reconcile; rollback instructions work |
| Legacy controls | Exercise original recording routes and advanced settings with V2 off/on | Explicitly document unsupported parity without silently activating dangerous operations |
| Security | Verify loopback host restriction, explicit `LAR_ALLOWED_HOSTS` and cross-origin rejects | Local/allowed hosts work, untrusted private IP/Origin requests denied |

The existing simulated unit tests cover several disk-full, publication, process
identity and missing-mount failure modes. They do **not** replace these real
device tests. Never intentionally disconnect a production NAS or fill a
production volume to satisfy a checklist.

## Evidence and release decision

Keep a separate, private evidence log containing the test timestamp, image
digest, exact host architecture, procedure, outcome, sanitized excerpts,
resource measurements, and operator approval. Mark every scenario pass/fail;
any missing/failed gate means **no V2 production promotion**.

Normal changes to `main` may publish the default V1 image through CI after
tests; that does not imply an approved V2 release. Retain a previously verified
image digest and restore by explicitly pinning `LIVE_AUTO_RECORDER_IMAGE` to it,
then recreate the container without deleting `data/` or recordings.
