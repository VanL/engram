from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from engram._constants import (
    DEFAULT_SQLITE_FILENAME,
    MEMORY_ID_LOGICAL_COUNTER_MASK,
    MEMORY_ID_MAX_LOGICAL_COUNTER,
    SQLITE_MAX_INT64,
)
from engram._exceptions import (
    MemoryItemNotFoundError,
    StoreDataError,
    StoreIntegrityError,
)
from engram._models import MemoryItem
from engram.store.id_generator import (
    decode_hybrid_memory_id,
    encode_hybrid_memory_id,
)
from engram.store.sqlite import SQLiteStateStore


def _aligned(physical_ns: int) -> int:
    return physical_ns & ~MEMORY_ID_LOGICAL_COUNTER_MASK


def _db_path(vault_path: Path) -> Path:
    return vault_path / DEFAULT_SQLITE_FILENAME


def _last_task_updated_at(vault_path: Path, item_id: int) -> int | None:
    connection = sqlite3.connect(_db_path(vault_path))
    try:
        rows = connection.execute(
            """
            SELECT last_task_updated_at
            FROM memory_items
            WHERE id = ?
            """,
            (item_id,),
        ).fetchall()
    finally:
        connection.close()
    assert len(rows) == 1
    value = rows[0][0]
    return int(value) if value is not None else None


def test_hybrid_memory_id_encoding_roundtrip() -> None:
    cases = (
        (1_754_685_000_000_000_000, 0),
        (1_754_685_000_000_000_123, 100),
        (1_754_685_000_000_000_999, MEMORY_ID_MAX_LOGICAL_COUNTER - 1),
        (2_000_000_000, 17),
    )

    for physical_ns, logical in cases:
        encoded = encode_hybrid_memory_id(physical_ns, logical)

        decoded_physical, decoded_logical = decode_hybrid_memory_id(encoded)

        assert decoded_physical == _aligned(physical_ns)
        assert decoded_logical == logical


def test_hybrid_memory_id_preserves_timestamp_magnitude() -> None:
    physical_ns = 1_754_685_000_000_000_000

    encoded = encode_hybrid_memory_id(physical_ns, 0)
    decoded_physical, _ = decode_hybrid_memory_id(encoded)

    assert str(encoded)[0] == str(physical_ns)[0]
    assert str(decoded_physical)[0] == str(physical_ns)[0]
    assert encoded == _aligned(physical_ns)


def test_hybrid_memory_id_rejects_invalid_components() -> None:
    with pytest.raises(StoreDataError):
        encode_hybrid_memory_id(-1, 0)

    with pytest.raises(StoreDataError):
        encode_hybrid_memory_id(1_000_000_000, -1)

    with pytest.raises(StoreDataError):
        encode_hybrid_memory_id(1_000_000_000, MEMORY_ID_MAX_LOGICAL_COUNTER)

    with pytest.raises(StoreDataError):
        encode_hybrid_memory_id(SQLITE_MAX_INT64, 0)

    with pytest.raises(StoreDataError):
        decode_hybrid_memory_id(-1)


def test_store_rejects_invalid_physical_timestamps(vault_path: Path) -> None:
    store = SQLiteStateStore(vault_path)
    try:
        with pytest.raises(StoreDataError):
            store.allocate_memory_id(-1)

        with pytest.raises(StoreDataError):
            store.allocate_memory_id(SQLITE_MAX_INT64)
    finally:
        store.close()


def test_memory_items_reject_negative_ids() -> None:
    with pytest.raises(ValueError):
        MemoryItem(
            id=-1,
            tier=0,
            text="Decision: memory IDs are non-negative.",
            created_at=1,
        )


def test_store_allocates_monotonic_ids_for_repeated_physical_time(
    vault_path: Path,
) -> None:
    store = SQLiteStateStore(vault_path)
    physical_ns = 1_754_685_000_000_000_123

    try:
        ids = [store.allocate_memory_id(physical_ns) for _ in range(4)]
    finally:
        store.close()

    assert ids == [
        _aligned(physical_ns),
        _aligned(physical_ns) + 1,
        _aligned(physical_ns) + 2,
        _aligned(physical_ns) + 3,
    ]


def test_store_reopen_preserves_memory_id_clock(vault_path: Path) -> None:
    physical_ns = 1_754_685_000_000_000_123
    store = SQLiteStateStore(vault_path)
    try:
        first_id = store.allocate_memory_id(physical_ns)
    finally:
        store.close()

    reopened = SQLiteStateStore(vault_path, create=False)
    try:
        second_id = reopened.allocate_memory_id(physical_ns)
    finally:
        reopened.close()

    assert second_id == first_id + 1


def test_store_memory_id_generator_reinitializes_after_pid_change(
    vault_path: Path,
) -> None:
    physical_ns = 1_754_685_000_000_000_123
    store = SQLiteStateStore(vault_path)
    try:
        first_id = store.allocate_memory_id(physical_ns)
        store._core._id_generator._pid = -1  # noqa: SLF001

        second_id = store.allocate_memory_id(physical_ns)
    finally:
        store.close()

    assert second_id == first_id + 1


def test_put_item_advances_memory_id_clock(vault_path: Path) -> None:
    store = SQLiteStateStore(vault_path)
    physical_ns = 1_754_685_000_000_000_123
    manual_id = _aligned(physical_ns) + 10
    try:
        store.put_item(
            MemoryItem(
                id=manual_id,
                tier=0,
                text="Decision: explicit store writes still advance the ID clock.",
                created_at=physical_ns,
            )
        )
        allocated_id = store.allocate_memory_id(physical_ns)
    finally:
        store.close()

    assert allocated_id == manual_id + 1


def test_multiple_store_handles_share_memory_id_clock(vault_path: Path) -> None:
    first = SQLiteStateStore(vault_path)
    second = SQLiteStateStore(vault_path, create=False)
    physical_ns = 1_754_685_000_000_000_123

    try:
        ids = [
            first.allocate_memory_id(physical_ns),
            second.allocate_memory_id(physical_ns),
            first.allocate_memory_id(physical_ns),
        ]
    finally:
        first.close()
        second.close()

    assert ids == [
        _aligned(physical_ns),
        _aligned(physical_ns) + 1,
        _aligned(physical_ns) + 2,
    ]


def test_summary_item_id_is_first_unused_after_max_child_id(
    vault_path: Path,
) -> None:
    store = SQLiteStateStore(vault_path)
    try:
        children = (
            (1_000_000_000, 900_000_000),
            (1_000_010_000, 900_010_000),
        )
        for item_id, created_at in children:
            store.put_item(
                MemoryItem(
                    id=item_id,
                    tier=0,
                    text=f"Decision: child item {item_id} for summary allocation.",
                    created_at=created_at,
                )
            )

        child_ids = [item_id for item_id, _ in children]
        episode = store.create_episode(
            text="Episode: summary allocation.",
            summary_terms=("summary", "allocation"),
            child_ids=child_ids,
        )
        stored_children = store.get_children(episode.id)
    finally:
        store.close()

    assert episode.id == max(child_ids) + 1
    assert episode.created_at == max(created_at for _, created_at in children)
    assert [child.id for child in stored_children] == child_ids


def test_summary_item_id_skips_existing_collision_after_child_anchor(
    vault_path: Path,
) -> None:
    store = SQLiteStateStore(vault_path)
    base = 1_000_000_000
    try:
        child_ids = [base, base + 10]
        for item_id in child_ids:
            store.put_item(
                MemoryItem(
                    id=item_id,
                    tier=0,
                    text=f"Decision: child item {item_id} for collision test.",
                    created_at=item_id,
                )
            )
        store.put_item(
            MemoryItem(
                id=base + 11,
                tier=0,
                text="Decision: occupied ID should be skipped.",
                created_at=base + 11,
            )
        )

        episode = store.create_episode(
            text="Episode: summary allocation collision.",
            summary_terms=("summary", "collision"),
            child_ids=child_ids,
        )
    finally:
        store.close()

    assert episode.id == base + 12


def test_summary_item_below_current_clock_does_not_allocate_from_clock(
    vault_path: Path,
) -> None:
    store = SQLiteStateStore(vault_path)
    future_ns = 1_754_685_000_000_000_123
    try:
        future_id = store.allocate_memory_id(future_ns)
        store.put_item(
            MemoryItem(
                id=future_id,
                tier=0,
                text="Decision: future item advances the clock.",
                created_at=future_ns,
            )
        )
        child_ids = [1_000_000_000, 1_000_010_000]
        for item_id in child_ids:
            store.put_item(
                MemoryItem(
                    id=item_id,
                    tier=0,
                    text=f"Decision: historical child item {item_id}.",
                    created_at=item_id,
                )
            )

        episode = store.create_episode(
            text="Episode: historical summary should stay historical.",
            summary_terms=("historical", "summary"),
            child_ids=child_ids,
        )
        next_future_id = store.allocate_memory_id(future_ns)
    finally:
        store.close()

    assert episode.id == max(child_ids) + 1
    assert episode.id < future_id
    assert next_future_id > future_id


def test_summary_item_above_clock_advances_memory_id_clock(vault_path: Path) -> None:
    store = SQLiteStateStore(vault_path)
    physical_ns = 1_000_000_000
    child_ids = [1_000_010_000, 1_000_020_000]
    try:
        for item_id in child_ids:
            store.put_item(
                MemoryItem(
                    id=item_id,
                    tier=0,
                    text=f"Decision: explicit child item {item_id}.",
                    created_at=physical_ns,
                )
            )

        episode = store.create_episode(
            text="Episode: summary above clock advances the clock.",
            summary_terms=("summary", "clock"),
            child_ids=child_ids,
        )
        generated_id = store.allocate_memory_id(physical_ns)
    finally:
        store.close()

    assert episode.id == max(child_ids) + 1
    assert generated_id > episode.id


def test_summary_item_rejects_missing_children(vault_path: Path) -> None:
    store = SQLiteStateStore(vault_path)
    try:
        store.put_item(
            MemoryItem(
                id=1_000_000_000,
                tier=0,
                text="Decision: one child exists.",
                created_at=1_000_000_000,
            )
        )

        with pytest.raises(MemoryItemNotFoundError):
            store.create_episode(
                text="Episode: missing children should fail.",
                summary_terms=("missing", "child"),
                child_ids=(1_000_000_000, 1_000_010_000),
            )

        summary_items = [item for item in store.all_items() if item.tier == 1]
    finally:
        store.close()

    assert summary_items == []


def test_summary_item_rejects_duplicate_children(vault_path: Path) -> None:
    store = SQLiteStateStore(vault_path)
    try:
        store.put_item(
            MemoryItem(
                id=1_000_000_000,
                tier=0,
                text="Decision: duplicate children should fail clearly.",
                created_at=1_000_000_000,
            )
        )

        with pytest.raises(StoreDataError):
            store.create_episode(
                text="Episode: duplicate children should fail.",
                summary_terms=("duplicate", "child"),
                child_ids=(1_000_000_000, 1_000_000_000),
            )

        summary_items = [item for item in store.all_items() if item.tier == 1]
    finally:
        store.close()

    assert summary_items == []


def test_summary_item_rejects_mismatched_explicit_created_at(
    vault_path: Path,
) -> None:
    store = SQLiteStateStore(vault_path)
    child_ids = [1_000_000_000, 1_000_010_000]
    try:
        for item_id in child_ids:
            store.put_item(
                MemoryItem(
                    id=item_id,
                    tier=0,
                    text=f"Decision: child item {item_id}.",
                    created_at=item_id,
                )
            )

        with pytest.raises(StoreDataError):
            store.create_episode(
                text="Episode: caller timestamp should not override support time.",
                summary_terms=("timestamp", "support"),
                child_ids=child_ids,
                created_at=max(child_ids) + 1,
            )

        summary_items = [item for item in store.all_items() if item.tier == 1]
    finally:
        store.close()

    assert summary_items == []


def test_summary_item_does_not_store_support_time_as_task_update_time(
    vault_path: Path,
) -> None:
    store = SQLiteStateStore(vault_path)
    child_ids = [1_000_000_000, 1_000_010_000]
    try:
        for item_id in child_ids:
            store.put_item(
                MemoryItem(
                    id=item_id,
                    tier=0,
                    text=f"Decision: child item {item_id}.",
                    created_at=item_id,
                )
            )

        episode = store.create_episode(
            text="Episode: support time is not task metadata.",
            summary_terms=("task", "metadata"),
            child_ids=child_ids,
        )
    finally:
        store.close()

    assert _last_task_updated_at(vault_path, episode.id) is None


def test_childless_summary_keeps_clock_allocator_fallback(vault_path: Path) -> None:
    store = SQLiteStateStore(vault_path)
    physical_ns = 1_754_685_000_000_000_123
    try:
        first_episode = store.create_summary_item(
            tier=1,
            text="Episode: childless explicit fixture one.",
            summary_terms=("summary", "allocation"),
            child_ids=(),
            created_at=physical_ns,
        )
        second_episode = store.create_summary_item(
            tier=1,
            text="Episode: childless explicit fixture two.",
            summary_terms=("summary", "allocation"),
            child_ids=(),
            created_at=physical_ns,
        )
    finally:
        store.close()

    assert first_episode.id == _aligned(physical_ns)
    assert first_episode.created_at == physical_ns
    assert second_episode.id == first_episode.id + 1


def test_store_cached_generator_recovers_from_clock_rollback(vault_path: Path) -> None:
    physical_ns = 1_754_685_000_000_000_123
    store = SQLiteStateStore(vault_path)
    try:
        first_id = store.allocate_memory_id(physical_ns)
        connection = sqlite3.connect(_db_path(vault_path))
        try:
            connection.execute(
                "UPDATE memory_id_clock SET last_memory_id = 0 WHERE singleton = 1"
            )
            connection.commit()
        finally:
            connection.close()

        second_id = store.allocate_memory_id(physical_ns)
    finally:
        store.close()

    assert second_id == first_id + 1


def test_store_rejects_clock_behind_existing_items_on_open(vault_path: Path) -> None:
    store = SQLiteStateStore(vault_path)
    physical_ns = 1_754_685_000_000_000_123
    try:
        allocated_id = store.allocate_memory_id(physical_ns)
        store.put_item(
            MemoryItem(
                id=allocated_id,
                tier=0,
                text="Decision: corrupted clocks must not allocate stale IDs.",
                created_at=physical_ns,
            )
        )
    finally:
        store.close()

    connection = sqlite3.connect(_db_path(vault_path))
    try:
        connection.execute(
            "UPDATE memory_id_clock SET last_memory_id = 0 WHERE singleton = 1"
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(StoreIntegrityError):
        SQLiteStateStore(vault_path, create=False)


def test_concurrent_store_allocations_are_unique(vault_path: Path) -> None:
    setup = SQLiteStateStore(vault_path)
    setup.close()
    physical_ns = 1_754_685_000_000_000_123
    workers = 8
    per_worker = 25

    def _allocate_many() -> list[int]:
        store = SQLiteStateStore(vault_path, create=False)
        try:
            return [store.allocate_memory_id(physical_ns) for _ in range(per_worker)]
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        batches = list(executor.map(lambda _: _allocate_many(), range(workers)))

    ids = [item_id for batch in batches for item_id in batch]
    expected = set(range(_aligned(physical_ns), _aligned(physical_ns) + len(ids)))

    assert len(ids) == workers * per_worker
    assert len(set(ids)) == len(ids)
    assert set(ids) == expected
