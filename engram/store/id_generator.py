"""Hybrid timestamp memory ID generation.

This module ports SimpleBroker's timestamp allocation model to Engram memory
IDs: keep IDs format-compatible with `time.time_ns()` values, reserve
low-order bits for a logical counter, and commit the last allocated value
through one atomic state-store update. Real clocks usually expose coarser than
nanosecond precision, so these low-order bits are normally zero or low-signal
physical time.

Spec references:
- docs/specs/10-minimum-memory-model.md [MM-3]
- docs/specs/15-foundation-contracts-and-invariants.md [FCI-1], [FCI-44]
"""

from __future__ import annotations

import os
import random
import threading
import time

from engram._constants import (
    MEMORY_ID_LOGICAL_COUNTER_MASK,
    MEMORY_ID_MAX_LOGICAL_COUNTER,
    MEMORY_ID_MAX_WAIT_ITERATIONS,
    MEMORY_ID_WAIT_FOR_NEXT_INCREMENT,
    SQLITE_MAX_INT64,
)
from engram._exceptions import StoreDataError, StoreIntegrityError
from engram.store.db import SQLRunner


def encode_hybrid_memory_id(physical_ns: int, logical: int) -> int:
    """Encode physical time and a logical counter into a memory ID.

    Args:
        physical_ns: Nanoseconds since epoch. Low-order counter bits are cleared.
        logical: Counter value for IDs allocated within the same time slice.

    Returns:
        SQLite-safe signed 64-bit integer memory ID.

    Spec:
        - [MM-3]
        - [FCI-1]
    """

    if physical_ns < 0:
        raise StoreDataError("memory ID physical timestamp cannot be negative")
    if logical < 0 or logical >= MEMORY_ID_MAX_LOGICAL_COUNTER:
        raise StoreDataError("memory ID logical counter is out of range")
    encoded = (physical_ns & ~MEMORY_ID_LOGICAL_COUNTER_MASK) | logical
    if encoded >= SQLITE_MAX_INT64:
        raise StoreDataError("memory ID timestamp is too far in the future")
    return encoded


def decode_hybrid_memory_id(item_id: int) -> tuple[int, int]:
    """Decode a memory ID into aligned physical time and logical counter."""

    if item_id < 0:
        raise StoreDataError("memory ID cannot be negative")
    return (
        item_id & ~MEMORY_ID_LOGICAL_COUNTER_MASK,
        item_id & MEMORY_ID_LOGICAL_COUNTER_MASK,
    )


class MemoryIdGenerator:
    """Thread-safe hybrid timestamp memory ID allocator."""

    def __init__(self, runner: SQLRunner) -> None:
        self._runner = runner
        self._lock = threading.Lock()
        self._initialized = False
        self._last_id = 0
        self._pid = os.getpid()

    def generate(self, physical_ns: int) -> int:
        """Allocate a globally unique memory ID for a physical timestamp."""

        if physical_ns < 0:
            raise StoreDataError("memory ID physical timestamp cannot be negative")
        self._ensure_pid()
        for _ in range(6):
            physical_base, logical = self._next_components(physical_ns)
            new_id = encode_hybrid_memory_id(physical_base, logical)
            if self._advance_last_id(new_id):
                with self._lock:
                    self._last_id = max(self._last_id, new_id)
                return new_id
            latest = self._read_last_id()
            with self._lock:
                self._last_id = max(self._last_id, latest)
                self._initialized = True
        raise StoreIntegrityError("unable to allocate unique memory ID")

    def get_cached_last_id(self) -> int:
        """Return the most recently observed memory ID without a fresh DB read."""

        with self._lock:
            if not self._initialized:
                self._last_id = self._read_last_id()
                self._initialized = True
            return self._last_id

    def refresh_last_id(self) -> int:
        """Refresh the cached memory ID clock from the state store."""

        latest = self._read_last_id()
        with self._lock:
            self._last_id = latest
            self._initialized = True
            return self._last_id

    def observe_existing_id(self, item_id: int) -> None:
        """Advance the clock to cover an externally supplied item ID."""

        if item_id < 0:
            raise StoreDataError("memory ID cannot be negative")
        if item_id >= SQLITE_MAX_INT64:
            raise StoreDataError("memory ID exceeds SQLite signed 64-bit range")
        self._advance_last_id(item_id)
        with self._lock:
            if item_id > self._last_id:
                self._last_id = item_id
            self._initialized = True

    def _ensure_pid(self) -> None:
        pid = os.getpid()
        if pid == self._pid:
            return
        with self._lock:
            self._pid = pid
            self._initialized = False
            self._last_id = 0

    def _next_components(self, physical_ns: int) -> tuple[int, int]:
        with self._lock:
            if not self._initialized:
                self._last_id = self._read_last_id()
                self._initialized = True

            last_physical, last_logical = decode_hybrid_memory_id(self._last_id)
            physical_base = physical_ns & ~MEMORY_ID_LOGICAL_COUNTER_MASK
            if physical_base > last_physical:
                return physical_base, 0

            logical = last_logical + 1
            if logical < MEMORY_ID_MAX_LOGICAL_COUNTER:
                return last_physical, logical

            return self._wait_for_next_physical_base(last_physical), 0

    def _wait_for_next_physical_base(self, last_physical: int) -> int:
        for _ in range(MEMORY_ID_MAX_WAIT_ITERATIONS):
            jitter = random.uniform(
                MEMORY_ID_WAIT_FOR_NEXT_INCREMENT / 2,
                MEMORY_ID_WAIT_FOR_NEXT_INCREMENT,
            )
            time.sleep(jitter)
            physical_base = time.time_ns() & ~MEMORY_ID_LOGICAL_COUNTER_MASK
            if physical_base > last_physical:
                return physical_base
        raise StoreIntegrityError("memory ID logical counter exhausted")

    def _read_last_id(self) -> int:
        rows = self._runner.run(
            """
            SELECT last_memory_id
            FROM memory_id_clock
            WHERE singleton = 1
            """
        )
        if len(rows) != 1:
            raise StoreIntegrityError("Engram state store memory ID clock is missing")
        last_id = int(rows[0][0])
        if last_id < 0:
            raise StoreIntegrityError("Engram state store memory ID clock is invalid")
        return last_id

    def _advance_last_id(self, new_id: int) -> bool:
        self._runner.run(
            """
            UPDATE memory_id_clock
            SET last_memory_id = ?
            WHERE singleton = 1
              AND last_memory_id < ?
            """,
            (new_id, new_id),
            fetch=False,
        )
        rows = self._runner.run("SELECT changes()")
        return bool(rows and int(rows[0][0]) > 0)
