"""Fail-closed storage resolution and optional non-destructive capability probes.

A read-only preflight never creates a directory, marker, database or probe file.
Configured mount markers are verified before any write, so an absent NAS mount
cannot silently turn into a new local recording directory.
"""
from __future__ import annotations
import os
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

NETWORK_FILESYSTEMS = frozenset({'nfs', 'nfs4', 'cifs', 'smbfs', 'smb3', 'fuse.sshfs', '9p', 'ceph', 'glusterfs'})

class StorageError(ValueError):
    code = 'STORAGE_UNAVAILABLE'

@dataclass(frozen=True)
class StorageRoot:
    storage_id: str
    root: Path | str
    marker: str | None = None
    expected_marker: str | None = None
    min_free_bytes: int = 0
    expected_device: int | None = None

    def __post_init__(self):
        object.__setattr__(self, 'root', Path(self.root).expanduser().absolute())

def _no_symlinks(path: Path, *, allow_missing=False):
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            if allow_missing:
                continue
            raise StorageError('A required storage path is missing')
        if stat.S_ISLNK(info.st_mode):
            raise StorageError('Symbolic links are not accepted in storage paths')

def resolve_storage_path(storage: StorageRoot, relative_path: str, *, must_exist=True) -> Path:
    root = Path(storage.root)
    if not isinstance(relative_path, str) or not relative_path or '\x00' in relative_path or '\\' in relative_path:
        raise StorageError('A nonempty relative POSIX path is required')
    relative = PurePosixPath(relative_path)
    if not relative.parts or relative.is_absolute() or any(part in ('..', '') for part in relative.parts):
        raise StorageError('Path traversal outside storage is not allowed')
    _no_symlinks(root)
    if not root.is_dir():
        raise StorageError('Storage root is not an existing directory')
    result = root.joinpath(*relative.parts)
    _no_symlinks(result, allow_missing=not must_exist)
    # String normalization is not an authorization check; containment is checked
    # independently and callers pin files with O_NOFOLLOW for the use-time race.
    try:
        result.relative_to(root)
    except ValueError as exc:
        raise StorageError('Path is outside storage') from exc
    if must_exist and not result.exists():
        raise StorageError('Input does not exist')
    return result

def filesystem_info(path: str | Path) -> dict[str, Any]:
    """Best-effort Linux mount inventory without changing mount state."""
    path = Path(path).absolute()
    best = {'mount_point': '', 'filesystem': 'unknown', 'mount_id': None}
    try:
        lines = Path('/proc/self/mountinfo').read_text().splitlines()
        for line in lines:
            fields = line.split()
            separator = fields.index('-')
            mountpoint = fields[4].replace('\\040', ' ').replace('\\011', '\t').replace('\\134', '\\')
            try:
                path.relative_to(Path(mountpoint))
            except ValueError:
                continue
            if len(mountpoint) >= len(best['mount_point']):
                best = {'mount_point': mountpoint, 'filesystem': fields[separator + 1], 'mount_id': fields[0]}
    except (OSError, ValueError, IndexError):
        pass
    return best

def preflight_storage(storage: StorageRoot, *, probe_writes=False) -> dict[str, Any]:
    root = Path(storage.root)
    report = {'ok': False, 'storage_id': storage.storage_id, 'errors': [], 'warnings': [], 'checks': {}}
    checks = report['checks']
    try:
        _no_symlinks(root)
        if not root.is_dir():
            raise StorageError('Storage root must already exist')
        info = root.stat()
        checks.update(filesystem_info(root))
        checks['device'] = info.st_dev
        if storage.expected_device is not None and info.st_dev != storage.expected_device:
            raise StorageError('Storage device identity changed')
        if storage.marker:
            marker = resolve_storage_path(storage, storage.marker)
            if not marker.is_file() or marker.stat().st_size > 4096:
                raise StorageError('Storage identity marker is invalid')
            if storage.expected_marker is not None and marker.read_text().strip() != storage.expected_marker:
                raise StorageError('Storage identity marker does not match')
            checks['marker'] = 'verified'
        elif storage.expected_marker is not None:
            raise StorageError('An expected marker requires a marker path')
        else:
            checks['marker'] = 'not_configured'
            report['warnings'].append('No persistent mount marker configured; set one for NAS fail-closed restart checks')
        usage = shutil.disk_usage(root)
        checks.update(free_bytes=usage.free, total_bytes=usage.total, writable=os.access(root, os.W_OK))
        if usage.free < storage.min_free_bytes:
            raise StorageError('Storage is below the configured free-space threshold')
        if probe_writes:
            if not checks['writable']:
                raise StorageError('Storage is not writable')
            # Only this uniquely named probe directory is removed. No existing
            # file is replaced, and no recording/configuration paths are touched.
            with tempfile.TemporaryDirectory(prefix='.lar-v2-probe-', dir=root) as work:
                source, final = Path(work) / 'probe.tmp', Path(work) / 'probe.link'
                with source.open('xb') as handle:
                    handle.write(b'lar-v2-storage-probe\n')
                    handle.flush()
                    os.fsync(handle.fileno())
                os.link(source, final)
                if not os.path.samefile(source, final):
                    raise StorageError('No-clobber hardlink publication is unsupported')
                flags = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0)
                directory_fd = os.open(work, flags)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
                checks['temporary_write'] = checks['hardlink_publication'] = checks['directory_fsync'] = True
        else:
            checks['temporary_write'] = checks['hardlink_publication'] = 'not_probed'
        report['ok'] = True
    except (OSError, ValueError) as exc:
        report['errors'].append(str(exc))
    return report

def preflight_database_location(data_dir: str | Path, *, min_free_bytes=16 * 1024 * 1024) -> dict[str, Any]:
    path = Path(data_dir).expanduser().absolute()
    report = {'ok': False, 'errors': [], 'checks': filesystem_info(path)}
    try:
        _no_symlinks(path)
        if not path.is_dir():
            raise StorageError('Data directory must already exist')
        fs = report['checks']['filesystem']
        if fs in NETWORK_FILESYSTEMS or fs.startswith(('fuse.sshfs', 'fuse.rclone')):
            raise StorageError('SQLite WAL metadata must use a local persistent filesystem')
        report['checks']['free_bytes'] = shutil.disk_usage(path).free
        if report['checks']['free_bytes'] < min_free_bytes:
            raise StorageError('Insufficient free space for SQLite metadata and backups')
        if not os.access(path, os.W_OK):
            raise StorageError('Data directory is not writable')
        report['ok'] = True
    except (OSError, ValueError) as exc:
        report['errors'].append(str(exc))
    return report
