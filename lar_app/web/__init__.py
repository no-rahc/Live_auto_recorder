"""Web delivery helpers used by the application bootstrap."""

from lar_app.web.assets import HTML_ROUTES, inject_console_assets
from lar_app.web.middleware import ConsoleAssetsMiddleware, SecurityMiddleware

__all__ = [
    "ConsoleAssetsMiddleware",
    "HTML_ROUTES",
    "SecurityMiddleware",
    "inject_console_assets",
]
