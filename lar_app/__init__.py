"""Application assembly package for Live Auto Recorder.

The legacy recorder core remains in ``live_auto_recorder.py`` while this package
owns deployment bootstrap, release metadata, middleware, and web asset wiring.
Keeping those concerns here prevents the executable entrypoint from becoming a
second application module.
"""

from lar_app.bootstrap import ApplicationRuntime, build_application
from lar_app.release import ReleaseInfo
from lar_app.server import ServerSettings, run_server

__all__ = [
    "ApplicationRuntime",
    "ReleaseInfo",
    "ServerSettings",
    "build_application",
    "run_server",
]
