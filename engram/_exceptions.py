"""Custom exceptions for Engram.

Spec references:
- docs/specs/10-minimum-memory-model.md [MM-19], [MM-21]
- docs/specs/11-minimum-write-search-context-slice.md [MWS-33], [MWS-34]
- docs/specs/15-foundation-contracts-and-invariants.md [FCI-14]
"""

from __future__ import annotations


class EngramError(Exception):
    """Base exception for Engram failures."""


class EngramClosedError(EngramError, RuntimeError):
    """Raised when an `EngramClient` operation is used after close.

    Spec:
        - [FCI-14]
    """


class MemoryItemNotFoundError(EngramError, KeyError):
    """Raised when a memory item cannot be found.

    Args:
        item_id: Shared Engram item ID.
        tier: Optional expected tier.

    Spec:
        - [MWS-18]
    """

    def __init__(self, item_id: int, tier: int | None = None) -> None:
        tier_suffix = f" at tier {tier}" if tier is not None else ""
        super().__init__(f"Memory item {item_id}{tier_suffix} not found")
        self.item_id = item_id
        self.tier = tier


class InvalidMemoryTextError(EngramError, ValueError):
    """Raised when memory text is empty or whitespace only."""


class InvalidImportanceError(EngramError, ValueError):
    """Raised when write-time importance is not a positive integer."""


class StoreConsistencyError(EngramError, RuntimeError):
    """Raised when state-store and index state diverge unexpectedly."""


class StoreError(EngramError, RuntimeError):
    """Base class for backend-neutral state-store failures."""


class StoreOperationalError(StoreError):
    """Raised for retry-exhausted or backend operational state-store failures."""


class StoreIntegrityError(StoreError):
    """Raised for state-store integrity constraint failures."""


class StoreDataError(StoreError):
    """Raised for invalid or unrepresentable state-store data."""


class StoreVersionError(StoreError):
    """Raised when a state-store schema version cannot be opened safely."""


class StoreBackendNotSupportedError(StoreError):
    """Raised when a configured state-store backend is unavailable."""


class InvalidStorePathError(StoreError, ValueError):
    """Raised when a database path fails hardening checks."""


class ProcessingError(EngramError, RuntimeError):
    """Raised when background item processing cannot complete."""


class VaultNotFoundError(EngramError, FileNotFoundError):
    """Raised when a vault path does not exist."""

    def __init__(self, path: str) -> None:
        super().__init__(f"Vault does not exist: {path}")
        self.path = path


class VaultNotInitializedError(EngramError, RuntimeError):
    """Raised when a directory exists but is not an initialized vault."""

    def __init__(self, path: str) -> None:
        super().__init__(f"Vault is not initialized: {path}")
        self.path = path
