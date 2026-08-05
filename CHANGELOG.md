# Changelog

## v1.1.7 - 2026-08-05

- Rebalanced the recording status page so wide screens use a compact three-column channel grid instead of stretching two cards across the full content width.
- Reduced channel card spacing, typography, metadata padding, and action height while preserving the full 16:9 thumbnail and all recording controls.
- Added responsive checks for compact desktop, two-column tablet, and single-column mobile channel layouts.

## v1.1.6 - 2026-08-05

- Added an operations center for storage protection, recording health, post-processing jobs, backups, statistics, channel rules, and audit history.
- Added recording start blocking below a configurable free-space threshold and safe cleanup previews that always protect active and recently modified files.
- Added file-growth health monitoring, stalled recording detection, bounded automatic reconnection, maximum recording duration, and low-storage notifications.
- Added configurable title, category, weekday, time-window, start-delay, quality, maximum-duration, and short-recording cleanup rules per channel.
- Added scheduled backups, pre-restore safety backups, optional secret inclusion, download and restore controls.
- Added post-processing job tracking with progress states, cancellation, and retry controls.
- Added 14-day and channel-level recording statistics with CSV export and storage estimates.
- Added login throttling, security response headers, and mutation audit logging.
- Added `linux/arm64` Docker images and a pull-request multi-platform build check.
- Added unit and responsive UI tests for the new operational features.

## v1.1.5 - 2026-08-05

- Standardized version updates around the root `VERSION` file and a reusable release helper.
- Added automated checks for synchronized release metadata and Conventional Commit PR titles.
- Added a consistent pull request template and documented the full release workflow.
- Reorganized the README into a deployment-focused product page with quick start, updates, storage, operations, troubleshooting, and security guidance.
- Added a Docker publish preflight check so inconsistent release metadata cannot be published.

## v1.1.4

- Consolidated the layered dashboard overrides into one light-first UI stylesheet and one interaction controller.
- Rebalanced the desktop layout around a 244 px sidebar and a 1240 px bounded content area.
- Added responsive layout checks for 1920, 1600, 1366, 768, and 390 px viewports.
- Added toast feedback for save and network failures, retry actions, destructive-action confirmation, and submit progress states.
- Added unsaved-change tracking for settings, cookies, and channel edit forms.
- Added loading skeletons and expandable long paths/file names.
- Reduced system metrics to CPU, memory, live network traffic, and one recording volume.
- Moved the canonical application version to the root `VERSION` file for consistent UI and Docker tags.
