# Application architecture

Live Auto Recorder keeps the original recorder implementation compatible while
moving deployment and web-delivery concerns into explicit packages. The goal is
to make changes local: editing middleware should not require touching the
recorder engine, and adding a stylesheet should not require editing the process
entrypoint.

## Directory responsibilities

```text
app_entry.py                 Process entrypoint and compatibility exports only
lar_app/                     Production application assembly
  bootstrap.py               Installs extensions, lifespan, and middleware
  release.py                 Reads VERSION and updates template globals
  server.py                  Validates HOST, PORT, and LOG_LEVEL
  web/
    assets.py                 Ordered CSS/JavaScript manifest and HTML injection
    middleware.py             Security policy, throttling, audit, asset delivery
module/                      Recorder and operational domain implementation
templates/                   Jinja pages and browser assets
scripts/                     Release and maintenance commands
docs/                        Operator and developer documentation
```

## Dependency direction

```text
app_entry
  -> lar_app.bootstrap
       -> lar_app.release
       -> lar_app.web
       -> module.config_tools_v1
       -> module.operations_v2
       -> live_auto_recorder (legacy core)
```

Lower layers must not import `app_entry.py`. Pure helpers such as release parsing,
asset rendering, and server settings must remain importable without starting the
recorder core.

## Where new code belongs

- Process startup, environment parsing, middleware, or global web assets:
  `lar_app/`.
- Recording, metadata, platform adapters, persistence, or post-processing:
  `module/` until the legacy core is split further.
- API routes that belong to one operational feature: keep route registration in
  that feature's installer and implementation in focused service modules.
- Page-specific CSS and JavaScript: `templates/static/`; register global assets
  once in `lar_app/web/assets.py`.
- Cross-page UI behavior: use one shared asset rather than adding another patch
  file from `app_entry.py`.

## Compatibility boundary

`live_auto_recorder.py` remains the compatibility core because existing routes,
state attributes, and external deployments depend on it. Refactors should first
extract pure helpers or services, then leave a small forwarding function at the
old import path. Avoid renaming public routes or `app.state` attributes in the
same change as a file move.

## Validation

Before merging structural changes, run:

```bash
python -m compileall -q app_entry.py lar_app module
python scripts/release.py check
```

Docker build checks also compile the production packages and run a live container
smoke test for the dashboard and management endpoints.

## Next extraction targets

The next safe refactor stages are:

1. Split route registration from `live_auto_recorder.py` into router modules
   while preserving route paths and dependency functions.
2. Move channel/config persistence behind small repository interfaces.
3. Consolidate page-level CSS patches after their visual behavior is verified in
   the running dashboard.
4. Replace version-suffixed internal module names only after compatibility shims
   and migration tests exist.
