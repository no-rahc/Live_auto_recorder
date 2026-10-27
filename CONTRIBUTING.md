# Contributing

## Before opening an issue

- Check existing issues first.
- Remove cookies, tokens, usernames, private paths, and channel identifiers from logs.
- Include the application version, Docker tag, platform, and relevant logs.
- Report security problems through `SECURITY.md`, not a public issue.

## Development

```bash
python -m pip install -r requirements.txt
python app_entry.py
```

## Embedded library development

The broadcast library and job status use the existing Python-served v1 console.
Run `npm ci` in `frontend`, then `npm run dev` to rebuild embedded assets on
changes while `python app_entry.py` serves `/broadcasts` and `/jobs`. There is no
separate frontend dashboard or Vite app server. Reading the library does not
require enabling the opt-in durable engine.

## Checks

```bash
python -m compileall -q app_entry.py live_auto_recorder.py lar_app module
# Install Node.js 22+ for JavaScript/UI regressions.
python scripts/test_regressions.py
python scripts/release.py check
```

The regression workflow runs on every pull request and every push to `main`,
without path filters. Missing Node.js or any skipped test fails the suite.

## Pull requests

- Keep one change per pull request.
- Use a Conventional Commit title such as `fix(recording): handle stalled process`.
- Validate the affected runtime path locally when behavior changes.
- Do not commit runtime data, recordings, cookies, tokens, generated reports, or local `.env` files.
- Keep `app_entry.py` thin. Put application assembly in `lar_app/` and recording domain logic in `module/`.
