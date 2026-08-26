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
})

INJECTION_MARKER = "data-lar-console"
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
    Asset("/static/css/console.css", "data-lar-console"),
)

HEAD_SCRIPTS = (
    Asset("/static/js/metrics.js", "data-lar-metrics"),
)

BODY_SCRIPTS = (
    Asset("/static/js/console.js", "data-lar-console", defer=True),
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
