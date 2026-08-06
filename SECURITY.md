# Security Policy

## Supported versions

Security fixes are applied to the latest release. Older Docker tags may not receive backports.

## Reporting a vulnerability

Do not open a public issue for vulnerabilities, leaked cookies, tokens, account data, or private recording paths.

Use GitHub's **Security → Report a vulnerability** form and include:

- affected version or Docker tag
- deployment method
- steps to reproduce
- expected and actual behavior
- logs with secrets removed

If a credential may have been exposed, revoke or rotate it before sending the report.

## Deployment notes

The default Compose configuration binds the web interface to `127.0.0.1` and requires login. Only set `APP_BIND_ADDRESS=0.0.0.0` after configuring access control. When serving through HTTPS, set `SESSION_HTTPS_ONLY=true`.

Backups containing cookies, account data, or notification tokens are disabled unless `ALLOW_SECRET_BACKUPS=true` is set explicitly.
