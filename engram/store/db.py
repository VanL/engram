"""Backend-neutral SQL runner primitives.

The runner layer mirrors the simplebroker split: domain code talks to a small
SQLRunner abstraction, while backend adapters own connection lifecycle,
defensive setup, retry, and database-driver exception translation.

Spec references:
- docs/specs/12-local-app-surface.md [LAS-4]
- docs/specs/15-foundation-contracts-and-invariants.md [FCI-44]
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, TypeVar

from engram._constants import SQLITE_BUSY_TIMEOUT_MS
from engram._exceptions import (
    StoreDataError,
    StoreIntegrityError,
    StoreOperationalError,
)

try:
    import fcntl
except ImportError:  # pragma: no cover - non-Unix fallback
    fcntl = None  # type: ignore[assignment]

QueryParams = Sequence[Any] | Mapping[str, Any]
T = TypeVar("T")


class SetupPhase(Enum):
    """State-store setup phase names."""

    CONNECTION = "connection"
    OPTIMIZATION = "optimization"


class SQLRunner(Protocol):
    """Small SQL execution surface shared by SQLite and future PG backends."""

    def run(
        self,
        sql: str,
        params: QueryParams = (),
        *,
        fetch: bool = True,
    ) -> list[tuple[Any, ...]]:
        """Execute one SQL statement."""

    def run_many(self, sql: str, params: Iterable[QueryParams]) -> None:
        """Execute one SQL statement for each parameter set."""

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Run statements in one write transaction."""
        yield

    def close(self) -> None:
        """Close resources owned by the runner."""


def interruptible_sleep(seconds: float, *, interval: float = 0.05) -> None:
    """Sleep in small chunks so signal handling and tests stay responsive."""

    deadline = time.monotonic() + seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(interval, remaining))


def execute_with_retry[T](
    operation: Callable[[], T],
    *,
    attempts: int = 5,
    initial_delay: float = 0.01,
    max_delay: float = 0.25,
) -> T:
    """Run an operation with exponential retry for transient SQLite locks."""

    delay = initial_delay
    last_error: sqlite3.OperationalError | None = None
    for attempt in range(attempts):
        try:
            return operation()
        except sqlite3.OperationalError as exc:
            if not _is_retryable_sqlite_error(exc):
                raise
            last_error = exc
            if attempt == attempts - 1:
                break
            interruptible_sleep(delay)
            delay = min(delay * 2, max_delay)
    if last_error is None:  # pragma: no cover - defensive
        raise StoreOperationalError("SQLite operation failed without an exception")
    raise StoreOperationalError("SQLite operation failed after retries") from last_error


def _is_retryable_sqlite_error(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return "database is locked" in message or "database is busy" in message


class SQLiteRunner:
    """SQLite implementation of SQLRunner."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._local = threading.local()
        self._connections: list[sqlite3.Connection] = []
        self._connections_lock = threading.Lock()
        self._pid = os.getpid()

    def run(
        self,
        sql: str,
        params: QueryParams = (),
        *,
        fetch: bool = True,
    ) -> list[tuple[Any, ...]]:
        """Execute one SQL statement and return tuple rows when requested."""

        def _execute() -> list[tuple[Any, ...]]:
            cursor = self._connection().execute(sql, params)
            if not fetch:
                cursor.close()
                return []
            rows = [tuple(row) for row in cursor.fetchall()]
            cursor.close()
            return rows

        return self._translate_errors(lambda: execute_with_retry(_execute))

    def run_many(self, sql: str, params: Iterable[QueryParams]) -> None:
        """Execute one SQL statement for each parameter set."""

        parameter_sets = tuple(params)

        def _execute() -> None:
            self._connection().executemany(sql, parameter_sets)

        self._translate_errors(lambda: execute_with_retry(_execute))

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Run statements inside `BEGIN IMMEDIATE`."""

        self.run("BEGIN IMMEDIATE", fetch=False)
        try:
            yield
            self.run("COMMIT", fetch=False)
        except Exception:
            self.run("ROLLBACK", fetch=False)
            raise

    @contextmanager
    def setup_lock(self, phase: SetupPhase) -> Iterator[None]:
        """Serialize schema/setup work across processes."""

        lock_path = self.db_path.with_name(f"{self.db_path.name}.{phase.value}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("w", encoding="utf-8") as handle:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def close(self) -> None:
        """Close all open SQLite connections owned by this runner."""

        with self._connections_lock:
            connections = list(self._connections)
            self._connections.clear()
        for connection in connections:
            connection.close()
        self._local.connection = None

    def _connection(self) -> sqlite3.Connection:
        self._reset_after_fork_if_needed()
        connection = getattr(self._local, "connection", None)
        if connection is None:
            connection = sqlite3.connect(
                self.db_path,
                isolation_level=None,
                timeout=SQLITE_BUSY_TIMEOUT_MS / 1000,
            )
            with self._connections_lock:
                self._connections.append(connection)
            self._local.connection = connection
        return connection

    def _reset_after_fork_if_needed(self) -> None:
        pid = os.getpid()
        if pid == self._pid:
            return
        self._pid = pid
        self._local = threading.local()
        with self._connections_lock:
            self._connections.clear()

    def _translate_errors(self, operation: Callable[[], T]) -> T:
        try:
            return operation()
        except sqlite3.IntegrityError as exc:
            raise StoreIntegrityError(str(exc)) from exc
        except sqlite3.DataError as exc:
            raise StoreDataError(str(exc)) from exc
        except sqlite3.OperationalError as exc:
            raise StoreOperationalError(str(exc)) from exc
