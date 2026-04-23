"""State backend protocol for Engram stores.

Spec references:
- docs/specs/15-foundation-contracts-and-invariants.md [FCI-44]
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from engram.store.db import SQLRunner


class StateBackend(Protocol):
    """Backend adapter responsible for setup and SQL dialect selection."""

    name: str

    def setup(self, runner: SQLRunner, *, create: bool, vault_path: Path) -> None:
        """Initialize or migrate backend state."""
