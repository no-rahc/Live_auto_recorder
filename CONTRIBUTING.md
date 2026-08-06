# Contributing

## Before opening an issue

- Check existing issues first.
- Remove cookies, tokens, usernames, private paths, and channel identifiers from logs.
- Include the application version, Docker tag, platform, and relevant logs.
- Report security problems through `SECURITY.md`, not a public issue.

## Development

```bash
python -m pip install -r requirements.txt
npm ci
python app_entry.py
```

## Checks

```bash
python -m compileall -q app_entry.py lar_app module
python -m unittest discover -s tests -p 'test_*_v1.py' -v
python -m unittest discover -s tests -p 'test_operations_v2.py' -v
npm run test:ui
python scripts/release.py check
```

## Pull requests

- Keep one change per pull request.
- Use a Conventional Commit title such as `fix(recording): handle stalled process`.
- Add or update tests when behavior changes.
- Do not commit runtime data, recordings, cookies, tokens, generated reports, or local `.env` files.
- Keep `app_entry.py` thin. Put application assembly in `lar_app/` and recording domain logic in `module/`.
