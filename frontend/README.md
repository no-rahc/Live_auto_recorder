# Live Auto Recorder v2 UI

Additive React + TypeScript + Vite UI at `/v2`. FastAPI serves the generated files;
Node is a build-time tool only. The existing `/` dashboard remains unchanged.

## Build

Requires Node.js 22.12+ (or 24) and npm.

```sh
cd frontend
npm ci
npm run build
```

Output: `templates/static/v2/index.html` and content-hashed files under `assets/`.
No runtime CDN, remote font, legacy `app.js`, or legacy `console.js` is loaded.
The Dockerfile builds the same assets in a separate Node stage.
Enable the server-side preview with `LAR_V2_ENABLED=true` only after completing
the storage and migration prerequisites in the v2 operations documentation.

For UI development, start the API on `127.0.0.1:5000`, then `npm run dev` and open
`http://127.0.0.1:5173/v2/`. Vite proxies `/api` to that API.

## Verification

```sh
npm test                  # API boundary, state ordering, command and screen tests
npm run build             # Strict TypeScript check + production asset build
npx playwright install --with-deps chromium
npm run test:browser      # Desktop and 360px browser regression suite
```

Browser tests start a read-only loopback static server with intercepted API
fixtures. They exercise navigation, UTC date filters, duplicate clicks,
conflicts, connection loss, pending commands/cancellation, and merge previews.
Use `PLAYWRIGHT_CHROMIUM_EXECUTABLE=/path/to/chromium` to select an existing
Chromium installation. Running browsers needs ordinary browser process and IPC
permissions; do not weaken sandbox/security settings to run the tests.

`tests/serve_real_app.py` is an optional full-app integration host. It copies
application code to a disposable temporary directory, uses empty channel/config
fixtures, and generates synthetic media. It never uses an installation's real
configuration, secrets, databases, or recordings. The fixture sets
`LAR_DISABLE_UPDATE_CHECK=true` to prevent the normal release-version check from
accessing GitHub. The fixture exits nonzero
if the child app cannot start.

## State and actions

- TanStack Query owns server data. Filters, pagination, and selected broadcasts /
  jobs live in the URL. Inputs and confirmations remain component-local.
- Visible tabs poll every five seconds; hidden tabs every thirty seconds. Requests
  are cancellable and late observations/revisions cannot overwrite newer data.
- Mutation responses mean acceptance, not recording/job completion. The UI
  refetches real state, and command receipts are polled until a terminal state.
- An uncertain network retry reuses the same idempotency key. A conflict refreshes
  the affected server data and asks the user to review it before resubmitting.
- Stale data stay visible with a warning. Unknown timestamps, duration, file
  presence, and metrics are shown as unknown instead of fabricated values.
- Unix-second observations and ISO media timestamps are supported. Display times
  follow the browser timezone; date-range filters are explicitly UTC.
- Original files are always preserved. Merge previews use server-provided source
  order and submit the observed broadcast revision.

## Compatibility boundary

The five v2 screens provide dashboard, broadcast library/detail, channel intent /
commands, durable job details/control, and safe settings status. Channel creation,
quality/path editing, credentials, notification settings, backups/restores, and
advanced file operations explicitly open the existing protected screens. They
are not silently duplicated in v2. Archive jobs are inspectable, but no new
archive action is offered without a configured destination contract.

`src/types.ts` models the current read contract and optional observations.
Request schemas and validation are owned by the server. If the server adds or
changes a response field, update the fixtures and types together. Generated
OpenAPI response types are a remaining improvement once all response models
are formalized server-side.
