# Changelog

## v1.1.19 - 2026-08-26

- Improve recording runtime stability and recovery flow
- Move recording history reads to the SQLite catalog
- Refactor configuration routing and safety handling

## v1.1.18 - 2026-08-06

- Removed the persistent username, online indicator, and logout card from the bottom of the navigation sidebar.
- Local mode now shows navigation only, with no account or logout controls rendered in the console shell.
- Login-protected deployments keep access to logout through one compact accessible icon in the top bar instead of a full sidebar card.
- Added five-viewport browser checks for local and authenticated sidebar states, compact action sizing, and horizontal overflow.

## v1.1.17 - 2026-08-06

- Rebalanced dashboard, recording, files, and operations workspaces with page-specific maximum widths instead of one global 1240 px limit.
- Reduced mobile dashboard hero and system-card height while keeping the four core metrics in a compact two-column grid.
- Reordered mobile recording content so global controls and channel cards appear before compact system metrics, with search and filters collapsed on demand.
- Limited recording-card width on large monitors and shortened mobile thumbnails to prevent sparse or overly tall layouts.
- Hid the settings action bar until a change exists, reduced its mobile height, and suppress it while the virtual keyboard is open.
- Removed the management sidebar and top bar from login and account creation, creating a centered standalone authentication shell.
- Collapsed advanced channel-registration fields on mobile while keeping all existing defaults and submit behavior intact.
- Added explicit primary, secondary, and danger hierarchy to file-manager controls and show the mobile action bar only after a file is selected.
- Changed cookie cards to a natural 65/35 desktop ratio and made the fifth operations KPI span the mobile row, with a horizontal-tab overflow cue.
- Added five-viewport coordinate and interaction checks for every proportional refinement in this release.

## v1.1.16 - 2026-08-05

- Split the production entrypoint into a side-effect-free `lar_app` package for bootstrap, release metadata, server settings, middleware, and web asset registration.
- Reduced `app_entry.py` to a small compatibility entrypoint while preserving `app`, `operations`, `PROGRAM_NAME`, and `RELEASE_VERSION` exports.
- Replaced hard-coded CSS and JavaScript injection strings with a declarative asset manifest and idempotent HTML injection helpers.
- Moved login throttling, security headers, audit logging, and HTML response rebuilding into focused middleware classes with instance-local state.
- Updated Docker and CI validation to compile complete packages and validate every registered browser asset directly from the manifest.
- Added unit coverage for package boundaries, release propagation, server environment validation, asset uniqueness, escaping, and injection idempotence.
- Added architecture documentation and explicit dependency rules for future router, persistence, and UI consolidation work.

## v1.1.15 - 2026-08-05

- Reworked the operations-center button hierarchy so only the active tab and primary save action use the orange emphasis color.
- Changed the global refresh, preview, CSV, backup, and compact table actions to neutral outline controls with consistent 40 px sizing.
- Separated destructive cleanup into its own danger zone and kept deletion disabled until a non-empty preview is available.
- Added keyboard arrow navigation and synchronized ARIA tab and panel states across all operations sections.
- Converted operational checkboxes into compact option cards and tightened responsive action spacing on tablet and mobile screens.
- Added five-viewport browser checks for tab contrast, action hierarchy, cleanup safety state, keyboard navigation, and horizontal overflow.

## v1.1.14 - 2026-08-05

- Completed a project-wide UI consistency audit across dashboard, recording, settings, channels, cookies, files, operations, login, and account creation flows.
- Replaced always-open channel edit forms with compact summaries and explicit accessible edit toggles while preserving the existing save and delete handlers.
- Reorganized the channel registration form into a responsive field grid and added a clear empty state without changing channel input meanings.
- Grouped CHZZK and YouTube cookie guidance into responsive provider panels and masked sensitive cookie values behind explicit reveal controls.
- Reflowed the file-manager toolbar and mobile action bar, removed fixed input widths, and improved file modal roles, focus handling, and Escape behavior.
- Removed the nested-card appearance from login, aligned account creation with the same authentication layout, and added password visibility and match feedback.
- Added five-viewport interaction and screenshot coverage for channel management, cookies, files, login, and registration alongside the existing dashboard, recording, settings, and operations checks.

## v1.1.13 - 2026-08-05

- Standardized dashboard status chips to one fixed height, baseline, padding, and icon alignment.
- Rebuilt the collapsed desktop sidebar header so the logo and collapse control no longer overlap inside the 72 px rail.
- Normalized collapsed menu, account, and logout controls to compact square icon sizes and removed horizontal overflow.
- Added automatic enhancement for navigation links injected after sidebar initialization, including the operations center link.
- Normalized CHZZK and YouTube live-title fields before caching so recording cards use the current broadcast title consistently.
- Refresh active recording metadata every 10 seconds, retry preparation placeholders once after 4 seconds, and recheck placeholder cache entries on a shorter TTL.
- Fixed the synchronous metadata cache-fill path and added responsive browser checks that replace a stale `방송 준비 중` title while recording.
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
