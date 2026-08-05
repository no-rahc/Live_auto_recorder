# Live Auto Recorder

A self-hosted live-stream recording dashboard and automation service for CHZZK.

## Features

- Automatic live-channel detection and recording
- Recording status dashboard with live system metrics
- Channel, cookie, file, backup, and recording-history management
- Optional Telegram and Discord notifications
- CIFS-backed recording storage support
- Docker deployment with health checks and rotating logs
- Responsive light dashboard UI

## Quick start

```bash
docker compose build
docker compose up -d
```

The application expects runtime state and credentials to be mounted separately. Do not commit `json/`, cookies, OAuth files, webhook URLs, or personal channel configuration.

## Configuration

Create the runtime directories and seed the application configuration from the image or deployment template. Configure channels and notification providers through the web UI or the runtime JSON volume.

Important environment-specific values are intentionally omitted from this repository:

- Channel IDs and channel names
- Recording paths and CIFS mounts
- Telegram bot credentials
- Discord webhook URLs
- OAuth tokens and client secrets
- Hostnames, private IP addresses, and user-specific paths

## License

MIT. See [LICENSE](LICENSE).

## Disclaimer

This project is an independent self-hosted tool. Respect CHZZK, YouTube, and other platform terms of service, copyright, privacy, and local law when recording or redistributing content.
