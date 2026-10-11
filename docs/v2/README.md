# Live Auto Recorder 2.0 preview

This is an additive, opt-in implementation on top of the existing recording
engines. It is not a production 2.0 release declaration. The root version remains
unchanged until the release gates below have been met.

## Deployment boundaries

- One application process/container per data directory. The v2 OS instance lock
  is acquired before recording engines start. Do not run multiple Uvicorn workers.
- SQLite and job metadata require host-local persistent storage. A NAS's own
  local disk is suitable; an SMB/NFS-mounted SQLite WAL database is not.
- Existing media directories and recording names are preserved. Register media
  and archive roots before processing. A missing or unsafe root blocks the job.
- All new media outputs retain their original inputs. New archive jobs are
  local/NAS copies. Remote rclone jobs remain legacy operations and are not
  represented as safely migrated v2 jobs.
- Windows can use the legacy recorder; the v2 durable media worker fails closed
  where POSIX no-follow file-descriptor guarantees are unavailable.
- Keep the default loopback binding. Additional hostnames require
  `LAR_ALLOWED_HOSTS`; v2 mode rejects foreign Host/Origin browser requests.
  This is not an internet-facing multi-user authentication system.

## Try the new UI

Build `frontend` with `npm ci && npm run build`, then start the normal Python
entrypoint with `LAR_V2_ENABLED=true`. Open `/v2`. Container builds compile the
frontend in a build stage and serve static files through FastAPI; there is no
Node runtime server in the final image. The legacy `/` UI remains available.
Disabling the UI feature flag does not reverse any database migration or erase
new outputs, job history, or channel intent.

The dashboard, broadcast library, broadcast detail, channel controls, and job
queue share one React/TanStack Query data flow. New pages do not load legacy DOM
patching scripts. Advanced channel editing and existing settings/backup tools
remain clearly linked legacy screens during the transition.

## Persistence and restart

New job/channel state uses a sidecar v2 SQLite database. The existing recording
catalog remains the compatibility source for ongoing engine events; normalized
v2 artifacts retain legacy identity mappings. This is an additive projection,
not a destructive schema replacement or bidirectional configuration sync.

Jobs are committed before execution. Attempts carry generation-fenced leases.
Expired leases alone do not authorize relaunch: process identity and absence
must be established. Uncertain ownership blocks execution. Cancellation of a
running operation is a request until process termination is confirmed.

Temporary output belongs to its attempt. Validated output is published without
replacing a destination. Publication intent is durable before the file appears;
unresolved publication is reconciled on restart. Database and NAS writes are
not a cross-filesystem transaction, and power-loss zero loss is not promised.

Notification delivery keeps the existing durable queue. An acknowledgement
lost between external delivery and database commit may duplicate a notification.
V2 verification does not trigger legacy delete-after-archive policies.

## Rollback

Before enabling v2, stop recording, keep the current image digest, and create and
verify a consistent SQLite/configuration backup. Keep secrets private and leave
recording files in place. Run the migration dry-run first; inspect rejected rows
and counts. Do not overwrite the only backup.

Before new writes, restore the previous image plus pre-migration data after
stopping the application. After v2 has produced new media or state, preserve the
v2 database and inventory all new files before any rollback. Restore previous
metadata from backup and re-index new media explicitly. Merely disabling the UI
flag is not a downgrade or a configuration rollback. No automatic reverse
schema conversion is provided.

## Release gates still requiring real hardware

Do not promote this preview on unit-test counts alone. A release requires:

1. Actual CHZZK and YouTube record/stop/reconnect/verify/merge smoke tests on both
   amd64 and arm64. A multiarch image build does not prove ARM64 runtime behavior.
2. At least 24 hours on a representative NAS with recording plus postprocessing,
   tracking memory/CPU/I/O/WAL growth and queue delay.
3. Real mount disappearance/return, full disk and process/container-kill tests
   across claim, output, publication and database commit boundaries.
4. A stopped-service backup/restore rehearsal with representative existing data,
   recording path reconciliation and validated backup integrity.
5. Review of the preserved legacy advanced controls and unsupported transitions
   before claiming full screen or feature parity.

See `IMPLEMENTATION.md` for the twelve implementation slices and exact local
verification evidence. No remote push, PR, production deployment, or release is
implied by this preview.

## Storage marker and capture-crash reconciliation

V2 recording admission requires an existing `.lar-storage-id` file at
`RECORDINGS_ROOT`. Provision it deliberately on the intended mounted volume
before enabling v2. Do not create it automatically in an empty fallback mount
path. Set `LAR_V2_RECORDINGS_MARKER` to a different relative marker path and
`LAR_V2_RECORDINGS_MARKER_VALUE` to enforce a specific identity value. The worker
and capture admission both check it; a missing marker yields a visible block.
The path must be writable and have at least 64 MiB available; existing operations
policy can impose stricter free-space limits.

After an unclean app exit, `v2-capture-active.json` deliberately prevents any new
capture. Unlike new media jobs, the retained capture engines do not yet have a
fully gated durable launch contract. The marker covers the launch-to-PID-record
gap and includes known process identities. This is a safety block, not an
automatic recorder restart promise.

For recovery, stop the app; inspect and terminate any surviving recorder process
and descendants, confirming their PID/start-time/boot identity instead of killing
an unrelated reused PID. Preserve the marker and catalog for diagnosis. Only
once all prior capture processes are confirmed absent, move the marker aside
into a private diagnostic backup and restart. If ownership is uncertain, leave
the block in place. Normal verified shutdown removes the marker automatically.
Never remove it while the app is running. New durable verification/media jobs
recover independently through their fenced attempts/publication reconciliation.

Legacy automatic transcoding, detached split postprocessing, delete-after-merge,
delete-after-archive short-recording cleanup and legacy retention deletion are disabled in v2 mode. Use the
explicit durable merge/recovery controls; originals stay intact. Legacy live
configuration restore is blocked while v2 is enabled because it cannot reconcile
new intent/job state. Stop the service and follow the offline restore procedure.
Advanced bitrate transcoding and live restore parity are not claimed by this
preview.

## Reproducible local checks

From a Python environment with `requirements.txt` installed:

```
python scripts/test_regressions.py
python -m compileall -q app_entry.py lar_app module
python scripts/release.py check
python scripts/smoke_v2_media.py
python scripts/smoke_v2_app.py
cd frontend
npm ci
npm run build
npm test
npm run test:browser
```

The media smoke uses only temporary synthetic fixtures with real FFmpeg/FFprobe.
The app smoke copies code into a temporary empty-channel install, checks two
clean startup/shutdown cycles, then verifies a real SIGKILL/restart remains
blocked for capture reconciliation. Neither accesses a real platform account or
production recordings. Browser tests require a supported Chromium sandbox; their
absence must not be represented as visual/mobile validation.
