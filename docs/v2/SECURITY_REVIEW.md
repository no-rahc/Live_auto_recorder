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
