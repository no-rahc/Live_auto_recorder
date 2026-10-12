# Implementation slices and scope ledger

Baseline: `059f081c4f683b6ffa996b8fab5e7fe43ea6e731`.
This is a reviewable, opt-in preview. It is **not** a declaration that every
acceptance gate in the design or a production 2.0 release has been completed.

| Slice | Delivered locally | Remaining boundary |
|---|---|---|
| A1 contracts/fixtures | All original regression cases retained; new API, file preservation, lifecycle and failure regressions | Actual provider behavior still needs live smoke |
| A2 storage preflight | Local-WAL location check before initialize, minimum space, explicit mounted-volume marker, no-follow paths, no-clobber capability checks | Real NAS disconnect and performance tests |
| B1 model/repository | Sidecar SQLite Broadcast/Session/Segment/Artifact/Job/Attempt, legacy aliases/provenance, desired modes/commands, revision and fencing | Existing catalog remains engine compatibility source; this is not full ownership cutover |
| B2 migration | Default read-only dry-run, stopped-service acknowledgement, prior-image ID, consistent DB backups, sanitized config snapshots/checksums, phase manifest, idempotent import, malformed-row report | No automatic reverse schema migration or destructive version-pointer cutover. JSONL-only history is provenance, not guessed executable media targets |
| C1 durable verification | Commit-before-run, claim/lease/generation, bounded retry, cancellation, attempts, restart reconciliation, capture-completion enqueue | Interrupted legacy capture ownership is handled by conservative manual reconciliation |
| C2 media jobs | Original-preserving recover/remux/merge, private attempt output, validated hardlink publication, postlink crash reconciliation | Arbitrary bitrate transcoding/legacy detached conversion disabled under v2 |
| C3 archive/notification | Local/NAS durable archive copy with hash verification; existing notification queue bridge; legacy queue history preserved | Remote rclone remains its own legacy queue; no claim of exactly-once external delivery |
| D1 state/API | Desired/actual separation, expected revision, idempotent commands/jobs, same-broadcast suppression, explicit once/stop, legacy start/stop adapters | Unknown provider identity is conservatively suppressed; interrupted once commands need a new request. Request schemas are Pydantic/OpenAPI; frontend response types remain manually maintained pending generated response contracts |
| D2 interface | Original v1 dashboard/sidebar retained; React library/job islands at `/broadcasts` and `/jobs`; old `/v2` routes redirect | Integrated browser fixtures and final CI must be verified before merge |
| D3 library/jobs | Broadcast filters/detail, session/segment/artifact relations, merge preview, job attempts/cancel/retry, responsive layout implementation | Full visual/interaction parity not claimed without supported browser testing |
| E1 settings/channels | Original recording/channel/settings pages remain the single control surface; secret-safe existing API and offline restore guard | Live legacy restore remains disabled with the opt-in durable engine |
| E2 release validation | Mandatory regression suite, real synthetic FFmpeg media flow, DB/FK integrity, full isolated app clean/crash-restart smoke, frontend build/unit/DOM checks | Docker build locally unavailable; actual amd64/arm64 provider recordings, NAS fault/24-hour soak and visual browser checks remain release gates |

## Changed invariants

1. New media jobs never replace or remove original input files.
2. Job acceptance is not completion. Attempts, cancellation requests and actual
   observed results are separate; stale owners cannot commit.
3. Publication and database commit are reconciled after interruptions instead of
   silently rerunning an already-published side effect.
4. Capture admission is blocked on a missing storage identity marker, unresolved
   capture ownership or unsafe process-group finalization.
5. Legacy routes must not bypass the v2 job lifecycle or revive suppressed capture.
6. Configuration responses expose no stored secret values. Local mode rejects
   foreign browser mutation origins when v2 is enabled.

## Revert boundaries

The changes are additive behind `LAR_V2_ENABLED`. Turning it off restores the
legacy UI/engine policy but does not delete or downgrade sidecar data. Preserve
new media and v2 metadata before a code downgrade. Do not use feature-flag
rollback to ignore an unresolved capture-process marker. Follow the stopped-app
procedure in README for data restoration and process reconciliation.

## Verification record

The final review package contains exact commands and results in
`TEST_RESULTS.txt`. Focused intermediate passes are not substituted for the final
mandatory suite. Browser suite launch failure and real-hardware tests are marked
not run rather than passed.
