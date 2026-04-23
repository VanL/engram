"""Engram public API.

Spec references:
- docs/specs/10-minimum-memory-model.md [MM-1], [MM-19]
- docs/specs/11-minimum-write-search-context-slice.md [MWS-1], [MWS-27]
- docs/specs/12-local-app-surface.md [LAS-29], [LAS-30]
"""

from __future__ import annotations

from engram._constants import PROG_NAME, __version__
from engram._exceptions import (
    EngramClosedError,
    EngramError,
    InvalidImportanceError,
    InvalidMemoryTextError,
    InvalidStorePathError,
    MemoryItemNotFoundError,
    ProcessingError,
    StoreBackendNotSupportedError,
    StoreConsistencyError,
    StoreDataError,
    StoreError,
    StoreIntegrityError,
    StoreOperationalError,
    StoreVersionError,
    VaultNotFoundError,
    VaultNotInitializedError,
)
from engram._models import (
    ContextSection,
    ContextView,
    FailedItemRecord,
    MemoryItem,
    ProcessResult,
    RebuildResult,
    SearchResult,
    VaultStatus,
)
from engram.client import EngramClient
from engram.core.memory import Engram

__all__ = [
    "Engram",
    "EngramClient",
    "ContextSection",
    "ContextView",
    "EngramClosedError",
    "EngramError",
    "FailedItemRecord",
    "InvalidImportanceError",
    "InvalidMemoryTextError",
    "InvalidStorePathError",
    "MemoryItem",
    "MemoryItemNotFoundError",
    "ProcessingError",
    "ProcessResult",
    "RebuildResult",
    "SearchResult",
    "StoreBackendNotSupportedError",
    "StoreConsistencyError",
    "StoreDataError",
    "StoreError",
    "StoreIntegrityError",
    "StoreOperationalError",
    "StoreVersionError",
    "VaultNotFoundError",
    "VaultNotInitializedError",
    "VaultStatus",
    "PROG_NAME",
    "__version__",
]
