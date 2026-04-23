"""SQLite file validation helpers.

Spec references:
- docs/specs/12-local-app-surface.md [LAS-4]
- docs/specs/15-foundation-contracts-and-invariants.md [FCI-44]
"""

from __future__ import annotations

from pathlib import Path

from engram._exceptions import VaultNotInitializedError

_SQLITE_HEADER = b"SQLite format 3\x00"


def validate_existing_database_file(db_path: Path, *, vault_path: Path) -> None:
    """Validate an existing SQLite database path before opening it."""

    if not db_path.exists():
        return
    if not db_path.is_file():
        raise VaultNotInitializedError(str(vault_path))
    if db_path.stat().st_size == 0:
        return
    with db_path.open("rb") as handle:
        header = handle.read(len(_SQLITE_HEADER))
    if header != _SQLITE_HEADER:
        raise VaultNotInitializedError(str(vault_path))


def is_valid_database_file(db_path: Path) -> bool:
    """Return whether a file looks like a SQLite database."""

    if not db_path.exists() or not db_path.is_file():
        return False
    if db_path.stat().st_size == 0:
        return True
    with db_path.open("rb") as handle:
        return handle.read(len(_SQLITE_HEADER)) == _SQLITE_HEADER
