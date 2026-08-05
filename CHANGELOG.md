# Changelog

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
