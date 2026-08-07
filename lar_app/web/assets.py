"""Declarative HTML asset manifest and injection helpers."""
from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape


HTML_ROUTES = frozenset({
    "/",
    "/recording",
    "/config",
    "/channels",
    "/cookies",
    "/files",
    "/operations",
    "/register",
})

INJECTION_MARKER = "data-lar-ui-v3"
_VERSION_IN_TITLE = re.compile(
    r"(<title>[^<]*?)\s+v\d+\.\d+\.\d+(?:[.-][0-9A-Za-z.-]+)?\s*(</title>)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Asset:
    path: str
    marker: str
    defer: bool = False

    def stylesheet_tag(self, version: str) -> str:
        return f'<link rel="stylesheet" href="{self.path}?v={version}" {self.marker}>'

    def script_tag(self, version: str) -> str:
        defer = " defer" if self.defer else ""
        return f'<script src="{self.path}?v={version}"{defer} {self.marker}></script>'


STYLESHEETS = (
    Asset("/static/css/app-v3.css", "data-lar-ui-v3"),
    Asset("/static/css/dashboard-glance-v1.css", "data-lar-dashboard-glance-v1"),
    Asset("/static/css/dashboard-channel-modal-v1.css", "data-lar-dashboard-channel-modal-v1"),
    Asset("/static/css/recording-density-v1.css", "data-lar-recording-density-v1"),
    Asset("/static/css/operations-v2.css", "data-lar-operations-v2"),
    Asset("/static/css/operations-platform-v3.css", "data-lar-operations-platform-v3"),
    Asset("/static/css/ui-polish-v1.css", "data-lar-ui-polish-v1"),
    Asset("/static/css/config-workspace-v1.css", "data-lar-config-workspace-v1"),
    Asset("/static/css/config-safety-v1.css", "data-lar-config-safety-v1"),
    Asset("/static/css/config-overview-v2.css", "data-lar-config-overview-v2"),
    Asset("/static/css/project-ui-audit-v1.css", "data-lar-project-ui-audit-v1"),
    Asset("/static/css/project-ui-audit-fixes-v1.css", "data-lar-project-ui-audit-fixes-v1"),
    Asset("/static/css/operations-controls-v1.css", "data-lar-operations-controls-v1"),
    Asset("/static/css/ui-refinement-v1.css", "data-lar-ui-refinement-v1"),
    Asset("/static/css/ui-refinement-final-v1.css", "data-lar-ui-refinement-final-v1"),
    Asset("/static/css/sidebar-account-v1.css", "data-lar-sidebar-account-v1"),
)

HEAD_SCRIPTS = (
    Asset("/static/js/system-metrics-v2.js", "data-lar-metrics-v2"),
)

BODY_SCRIPTS = (
    Asset("/static/js/sidebar-v3.js", "data-lar-sidebar-v3", defer=True),
    Asset("/static/js/sidebar-account-v1.js", "data-lar-sidebar-account-v1", defer=True),
    Asset("/static/js/dashboard-v4.js", "data-lar-dashboard-v4", defer=True),
    Asset("/static/js/dashboard-channel-modal-v1.js", "data-lar-dashboard-channel-modal-v1", defer=True),
    Asset("/static/js/app-ui-v3.js", "data-lar-ui-v3", defer=True),
    Asset("/static/js/recording-live-meta-v1.js", "data-lar-recording-live-meta-v1", defer=True),
    Asset("/static/js/config-workspace-v1.js", "data-lar-config-workspace-v1", defer=True),
    Asset("/static/js/config-safety-v1.js", "data-lar-config-safety-v1", defer=True),
    Asset("/static/js/config-overview-v2.js", "data-lar-config-overview-v2", defer=True),
    Asset("/static/js/project-ui-audit-v1.js", "data-lar-project-ui-audit-v1", defer=True),
    Asset("/static/js/operations-v2.js", "data-lar-operations-v2", defer=True),
    Asset("/static/js/operations-controls-v1.js", "data-lar-operations-controls-v1", defer=True),
    Asset("/static/js/operations-platform-v3.js", "data-lar-operations-platform-v3", defer=True),
    Asset("/static/js/ui-refinement-v1.js", "data-lar-ui-refinement-v1", defer=True),
)

_CRITICAL_STYLE = (
    '<style data-lar-ui-v3-critical>'
    '@media (min-width:1100px){body.lar-sidebar-v3 .menu-icon{display:none!important}}'
    '</style>'
)


def _safe_version(version: str) -> str:
    return escape(str(version), quote=True)


def render_head_assets(version: str) -> str:
    safe_version = _safe_version(version)
    tags = ['<meta name="color-scheme" content="light">']
    tags.extend(asset.stylesheet_tag(safe_version) for asset in STYLESHEETS)
    tags.append(_CRITICAL_STYLE)
    tags.extend(asset.script_tag(safe_version) for asset in HEAD_SCRIPTS)
    return "".join(tags)


def render_body_assets(version: str) -> str:
    safe_version = _safe_version(version)
    return "".join(asset.script_tag(safe_version) for asset in BODY_SCRIPTS)


def strip_version_from_title(html: str) -> str:
    return _VERSION_IN_TITLE.sub(r"\1\2", html)


def inject_console_assets(html: str, version: str) -> str:
    """Inject the shared console assets exactly once into an HTML document."""

    normalized = strip_version_from_title(html)
    if INJECTION_MARKER in normalized:
        return normalized

    head_assets = render_head_assets(version)
    body_assets = render_body_assets(version)

    if "</head>" in normalized:
        normalized = normalized.replace("</head>", head_assets + "</head>", 1)
    else:
        normalized = head_assets + normalized

    if "</body>" in normalized:
        return normalized.replace("</body>", body_assets + "</body>", 1)
    return normalized + body_assets


def all_asset_paths() -> tuple[str, ...]:
    """Return every registered path for validation and diagnostics."""

    return tuple(asset.path for asset in (*STYLESHEETS, *HEAD_SCRIPTS, *BODY_SCRIPTS))
