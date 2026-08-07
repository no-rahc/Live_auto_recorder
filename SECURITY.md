# Security Policy

## Supported versions

Security fixes are applied to `main` and the current `latest` Docker image. Older version tags may not receive backports.

## Reporting a vulnerability

Do not open a public issue for vulnerabilities, leaked cookies, tokens, or private recording paths.

Use GitHub's **Security → Report a vulnerability** form and include:

- affected version or Docker tag
- deployment method
- steps to reproduce
- expected and actual behavior
- logs with secrets removed

If a credential may have been exposed, revoke or rotate it before sending the report.

## Deployment notes

The default deployment model is passwordless and local-only. Compose publishes the web interface only on `127.0.0.1`, and standalone execution also defaults to `127.0.0.1`.

Do not expose the application port directly on a LAN or the public internet. If remote access is required, place an authenticated tunnel or reverse proxy in front of the application and keep the recorder port private.

Backups containing cookies or notification/API tokens are disabled unless `ALLOW_SECRET_BACKUPS=true` is set explicitly.
