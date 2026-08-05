"""Production entrypoint for Live Auto Recorder.

Application assembly lives in :mod:`lar_app`; this module intentionally keeps
only the process entrypoint and compatibility exports used by deployments.
"""
from __future__ import annotations

from lar_app.bootstrap import build_application
from lar_app.server import run_server


runtime = build_application()
app = runtime.app
operations = runtime.operations
RELEASE_VERSION = runtime.release.version
PROGRAM_NAME = runtime.release.name


def main() -> None:
    run_server(app)


if __name__ == "__main__":
    main()
