from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from backend.core.errors import InsufficientDiskSpaceError

BYTES_PER_GB = 1024**3


@dataclass(frozen=True)
class DiskSpaceStatus:
    path: str
    free_bytes: int
    min_free_bytes: int

    @property
    def free_gb(self) -> float:
        return self.free_bytes / BYTES_PER_GB

    @property
    def min_free_gb(self) -> float:
        return self.min_free_bytes / BYTES_PER_GB

    @property
    def ok(self) -> bool:
        return self.free_bytes >= self.min_free_bytes


def check_free_space(download_path: str, min_free_space_gb: float) -> DiskSpaceStatus:
    path = existing_usage_path(Path(download_path))
    usage = shutil.disk_usage(path)
    min_free_bytes = int(min_free_space_gb * BYTES_PER_GB)
    status = DiskSpaceStatus(
        path=str(path),
        free_bytes=usage.free,
        min_free_bytes=min_free_bytes,
    )
    if not status.ok:
        raise InsufficientDiskSpaceError(
            "download disk free space is below the configured minimum "
            f"({status.free_gb:.2f} GB free, {status.min_free_gb:.2f} GB required)"
        )
    return status


def existing_usage_path(path: Path) -> Path:
    current = path
    while not current.exists():
        parent = current.parent
        if parent == current:
            return current
        current = parent
    return current
