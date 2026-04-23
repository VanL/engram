"""SQL namespace protocol for state-store queries.

Spec references:
- docs/specs/15-foundation-contracts-and-invariants.md [FCI-44]
"""

from __future__ import annotations

from typing import Protocol


class StateSQL(Protocol):
    """Backend SQL namespace consumed by StateStoreCore."""

    MEMORY_ITEM_COLUMNS: tuple[str, ...]
    FAILED_ITEM_COLUMNS: tuple[str, ...]
    MEMORY_ITEM_SELECT: str
    FAILED_ITEM_SELECT: str
