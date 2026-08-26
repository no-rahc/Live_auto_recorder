"""Shared subprocess policy for recorder backends.

Recorder processes are placed in their own process group/session so ChannelFsm can
reliably terminate the full tree on user stop, health recovery, and shutdown.
"""
from __future__ import annotations

import os
import subprocess
from typing import Any


def grouped_subprocess_kwargs() -> dict[str, Any]:
    """Return platform-specific kwargs for a recorder-owned process group."""

    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    if hasattr(os, "setsid"):
        return {"preexec_fn": os.setsid}
    return {}
