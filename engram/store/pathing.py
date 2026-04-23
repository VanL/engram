"""Path hardening helpers for Engram state stores.

Spec references:
- docs/specs/12-local-app-surface.md [LAS-4]
- docs/specs/15-foundation-contracts-and-invariants.md [FCI-44]
"""

from __future__ import annotations

import os
import re
from pathlib import Path, PurePath

from engram._exceptions import InvalidStorePathError

_SAFE_COMPONENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def validate_safe_path_components(path: str | PurePath) -> None:
    """Validate relative database path components.

    This helper is for backend-owned filenames and relative components. It is
    intentionally not applied to user-provided absolute vault paths, because
    absolute paths routinely contain spaces and platform-specific separators.
    """

    pure_path = PurePath(path)
    if pure_path.is_absolute():
        raise InvalidStorePathError(
            "path component validation requires a relative path"
        )
    for part in pure_path.parts:
        if part in {"", ".", ".."}:
            raise InvalidStorePathError(f"unsafe path component: {part!r}")
        if not _SAFE_COMPONENT_RE.fullmatch(part):
            raise InvalidStorePathError(f"unsafe path component: {part!r}")
        stem = part.split(".", maxsplit=1)[0].upper()
        if stem in _WINDOWS_RESERVED_NAMES:
            raise InvalidStorePathError(f"reserved path component: {part!r}")


def validate_database_parent_directory(db_path: Path) -> None:
    """Validate that a database parent directory is usable."""

    parent = db_path.parent
    if not parent.exists():
        raise InvalidStorePathError(f"database parent does not exist: {parent}")
    if not parent.is_dir():
        raise InvalidStorePathError(f"database parent is not a directory: {parent}")
    if not os.access(parent, os.R_OK | os.W_OK | os.X_OK):
        raise InvalidStorePathError(f"database parent is not accessible: {parent}")
