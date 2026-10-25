"""Writes files so that a crash never leaves a half-written file behind."""
from __future__ import annotations

import os
from pathlib import Path


def atomic_write(path: Path, data: bytes) -> None:
    """Writes to `path.tmp`, keeps the previous file as `path.bak` and renames the new one into place."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    if path.exists():
        os.replace(path, path.with_name(path.name + ".bak"))
    os.replace(tmp, path)
