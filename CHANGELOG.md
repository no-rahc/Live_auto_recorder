# Changelog

## v1.1.13 - 2026-08-05

- Standardized dashboard status chips to one fixed height, baseline, padding, and icon alignment.
- Rebuilt the collapsed desktop sidebar header so the logo and collapse control no longer overlap inside the 72 px rail.
- Normalized collapsed menu, account, and logout controls to compact square icon sizes and removed horizontal overflow.
- Added automatic enhancement for navigation links injected after sidebar initialization, including the operations center link.
- Added responsive browser checks for status-chip dimensions, delayed navigation links, collapsed sidebar width, hidden labels, account controls, and top-bar offsets.

## v1.1.12 - 2026-08-05

- Reorganized settings into five focused groups for recording, CHZZK, processing, notifications, and system/security.
- Removed duplicate backup and cleanup cards from settings and linked those tasks to the operations center.
- Added progressive disclosure so disabled plugins, split recording, post-processing, encoding, notifications, and file-manager options do not consume space.
- Added encoding profiles, live filename previews, recording-path diagnostics, and server encoder capability checks.
- Added a fixed unsaved-change bar with reset and save actions and hid desktop-only tray/window options in the container UI.
- Replaced the legacy settings masonry override with a single responsive settings workspace and automated interaction checks.

## v1.1.11 - 2026-08-05

- Replaced the dashboard modal's square automatic-recording checkbox with a compact orange switch and supporting description.
- Kept the switch visually clear in both view and edit modes while preserving keyboard focus and disabled-state behavior.
- Removed the inherited centered max-width from the desktop top bar so page context begins a consistent distance from the sidebar.
- Added responsive checks for the sidebar-to-topbar gap and the automatic-recording switch dimensions and colors.

## v1.1.10 - 2026-08-05

- Added a dashboard channel-details modal that opens from each channel status row.
- Added view and edit modes for channel name, recording path, quality, extension, watch-party filters, and automatic recording state.
- Kept platform and channel ID read-only, omitted destructive delete actions, and linked advanced management back to the channel management page.
- Added recording-state guidance so path and format changes are clearly marked as applying to the next recording session.
- Added keyboard access, unsaved-change confirmation, responsive mobile sheet layout, and automated API/save interaction checks.

## v1.1.9 - 2026-08-05

- Replaced the dashboard's stretched storage/resource split with four compact cards for storage, CPU, memory, and live network traffic.
- Removed the redundant empty volume section from the dashboard storage card.
- Added a responsive settings-card masonry layout so sections keep their natural height instead of inheriting blank space from taller neighboring cards.
- Tightened settings-card spacing and preserved a single ordered column on tablet and mobile screens.
- Added automated UI checks for dashboard system-card height and settings-page gap packing.

## v1.1.8 - 2026-08-05

- Reorganized the dashboard around a compact glance-first hierarchy with status, key counts, quick navigation, system metrics, and activity in that order.
- Replaced the oversized solid orange hero with a shorter light carrot-style status panel and removed the dashboard version badge.
- Converted quick navigation from a tall vertical list into a compact responsive shortcut row.
- Reduced dashboard metric and system-card height so storage, CPU, memory, and network information appear earlier on the first screen.
- Added responsive dashboard layout checks for desktop, tablet, and mobile viewports.

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
