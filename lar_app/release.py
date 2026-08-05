"""Release metadata loading and legacy-core synchronization."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_PROGRAM_NAME = "Live Auto Recorder"
DEFAULT_VERSION = "v0.0.0"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class ReleaseInfo:
    """Immutable release metadata shared by templates, assets, and Docker."""

    root_dir: Path
    name: str
    version: str

    @property
    def version_file(self) -> Path:
        return self.root_dir / "VERSION"


def _read_version(version_file: Path, fallback: str) -> str:
    try:
        value = version_file.read_text(encoding="utf-8").strip()
    except OSError:
        return fallback
    return value or fallback


def load_release_info(core: Any, root_dir: Path | None = None) -> ReleaseInfo:
    """Read canonical release metadata without mutating the recorder core."""

    root = (root_dir or PROJECT_ROOT).resolve()
    fallback_version = str(getattr(core, "PROGRAM_VERSION", DEFAULT_VERSION) or DEFAULT_VERSION)
    name = str(getattr(core, "PROGRAM_NAME", DEFAULT_PROGRAM_NAME) or DEFAULT_PROGRAM_NAME)
    version = _read_version(root / "VERSION", fallback_version)
    return ReleaseInfo(root_dir=root, name=name, version=version)


def apply_release_info(core: Any, release: ReleaseInfo) -> None:
    """Apply release metadata to the legacy module and Jinja environment."""

    core.PROGRAM_VERSION = release.version
    templates = getattr(core, "templates", None)
    environment = getattr(templates, "env", None)
    globals_map = getattr(environment, "globals", None)
    if globals_map is not None:
        globals_map.update(
            program_name=release.name,
            program_version=release.version,
        )
