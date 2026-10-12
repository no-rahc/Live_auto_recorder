# Security review of retained PR79 findings

Review performed against baseline `059f081` and this local v2 preview. No remote
review threads were resolved and no new CodeQL scan is represented here.

- PR79 discussion `4241799329`, `config_validation.py` root existence probe:
  intentional functionality. Canonicalization and protected-root rejection happen
  before the existence probe. Symlink aliases and platform drive roots are tested.
  This does not authorize arbitrary file access; actual file-operation scope is
  enforced separately.
- Discussions `4241799344`, `4241799347`, `4241799349`: application-authored
  `ConfigValidationError` messages, not arbitrary exception strings. Retained
  useful validation feedback and added comments/tests explaining the boundary.
- Discussion `4241799352`: genuine raw `ValueError`/`TypeError` response exposure.
  Replaced it and adjacent raw config import/export exception responses with safe
  fixed messages.

Additional issues addressed during the same pass:

- Recursively omit credential fields from config JSON read/save responses, keep
  runtime/stored values intact, and use no-store caching.
- Keep omitted credentials and unknown non-secret extension keys through updates.
- Never echo credential-bearing HTTP exceptions or upstream response bodies from
  Telegram/Discord test endpoints. Harden the duplicated legacy Telegram handler
  actually reached by the production route order as well as extracted routes.
- V2 opt-in mode rejects foreign Host/Origin changes consistently across retained
  routes; this is a local deployment defense, not a multi-user authorization layer.

Repository and media-worker review additionally found and fixed cancellation,
idempotency replay, active-input, revision, publication and capture-admission
integration issues. The release document lists the remaining real-hardware gates.

## PR82 initial CodeQL review

- Alert 77 / discussion 4243775547: genuine status-response exposure. Internal
  worker exceptions and storage diagnostics could contain private paths or
  credentials. Public status and readiness now allowlist health counters and uses fixed
  failure messages; an API regression injects a credential-bearing traceback.
- Alert 78 / discussion 4243775540: plaintext credential backup was a genuine
  exposure even inside an owner-only directory. The preview now rejects
  `--include-secrets` for both dry-run and apply, before any backup or import
  writes. Direct Python calls enforce the same restriction. The credential-file
  copy path has been removed, and JSON/JSONL snapshots always sanitize secrets.
  Original settings and credential files remain untouched. Regression tests
  cover CLI rejection, direct-call rejection, no-write behavior and sanitized
  migration. No remote alert was manually dismissed or suppressed; the new
  CodeQL scan determines whether the finding is resolved.

- Follow-up alert 79 marked the already-redacted JSONL write as a secret source:
  CodeQL's sensitive-function-name heuristic treats `sanitize_secrets` as a
  function returning secrets. Renamed this helper to `redact_secrets` to state
  its actual output contract (the upstream heuristic recognizes `redact`).
  Added an end-to-end regression proving nested password, API key, cookie,
  credential and webhook fields are absent from JSON and both JSONL backups,
  while non-secret data and every original file remain intact. No query,
  suppression, alert dismissal or security workflow was changed.
