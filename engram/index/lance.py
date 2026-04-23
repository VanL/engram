"""LanceDB retrieval index wrapper.

Spec references:
- docs/specs/10-minimum-memory-model.md [MM-20], [MM-21]
- docs/specs/11-minimum-write-search-context-slice.md [MWS-10], [MWS-11], [MWS-12]
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import lancedb  # type: ignore[import-untyped]
import pyarrow as pa
from lancedb.embeddings.base import (  # type: ignore[import-untyped]
    EmbeddingFunction,
    EmbeddingFunctionConfig,
)

from engram._constants import DEFAULT_LANCE_DIR_NAME, LANCE_TABLE_NAME
from engram._models import MemoryItem


class LanceIndex:
    """LanceDB-backed hybrid retrieval index."""

    def __init__(
        self,
        vault_path: Path,
        *,
        embedding_function: EmbeddingFunction,
    ) -> None:
        self._path = vault_path / DEFAULT_LANCE_DIR_NAME
        self._path.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(self._path)
        self._embedding_function = embedding_function
        self._table = self._open_or_create_table()
        self._ensure_fts_index()

    @property
    def path(self) -> Path:
        """Return the LanceDB directory path."""
        return self._path

    @property
    def embedding_function(self) -> EmbeddingFunction:
        """Return the embedding function backing this index."""
        return self._embedding_function

    def upsert_item(self, item: MemoryItem) -> None:
        """Upsert a searchable item."""
        self.delete_item(item.id)
        self._table.add([self._row_for_item(item)])

    def delete_item(self, item_id: int) -> None:
        """Delete an item from the index."""
        self._table.delete(f"id = {item_id}")

    def search_text(
        self,
        query: str,
        *,
        limit: int,
        tiers: Sequence[int] | None = None,
    ) -> list[dict[str, object]]:
        """Run full-text search."""
        rows = (
            self._table.search(
                query,
                query_type="fts",
                fts_columns="text",
            )
            .limit(limit)
            .to_list()
        )
        return self._filter_rows(rows, tiers=tiers)

    def search_vector(
        self,
        query: str | Sequence[float],
        *,
        limit: int,
        tiers: Sequence[int] | None = None,
    ) -> list[dict[str, object]]:
        """Run vector search using Lance-managed query embedding when possible."""
        vector_query: str | list[float]
        if isinstance(query, str):
            if self._has_registered_embedding_function():
                vector_query = query
            else:
                vector_query = self._query_embedding(query)
        else:
            vector_query = list(query)
        rows = (
            self._table.search(
                vector_query,
                query_type="vector",
                vector_column_name="vector",
            )
            .limit(limit)
            .to_list()
        )
        return self._filter_rows(rows, tiers=tiers)

    def rebuild(self, items: Sequence[MemoryItem]) -> None:
        """Rebuild the index from authoritative state."""
        self._db.drop_table(LANCE_TABLE_NAME, ignore_missing=True)
        self._table = self._open_or_create_table()
        rows = [self._row_for_item(item) for item in items]
        if rows:
            self._table.add(rows)
        self._ensure_fts_index(replace=True)

    def count_rows(self) -> int:
        """Return the indexed row count."""
        return int(self._table.count_rows())

    def close(self) -> None:
        """Release references to LanceDB resources."""

        self._table = None
        self._db = None

    def _open_or_create_table(self) -> Any:
        table_names = set(self._db.list_tables().tables)
        if LANCE_TABLE_NAME in table_names:
            table = self._db.open_table(LANCE_TABLE_NAME)
            functions = table.embedding_functions
            conf = functions.get("vector")
            if conf is not None:
                self._embedding_function = conf.function
            return table
        return self._db.create_table(
            LANCE_TABLE_NAME,
            schema=_table_schema(self._embedding_function),
            embedding_functions=[
                EmbeddingFunctionConfig(
                    source_column="text",
                    vector_column="vector",
                    function=self._embedding_function,
                )
            ],
        )

    def _ensure_fts_index(self, *, replace: bool = False) -> None:
        try:
            self._table.create_fts_index("text", replace=replace)
        except Exception:  # pragma: no cover - lancedb raises when index exists
            if replace:
                raise

    def _filter_rows(
        self,
        rows: Sequence[dict[str, Any]],
        *,
        tiers: Sequence[int] | None,
    ) -> list[dict[str, Any]]:
        if tiers is None:
            return [dict(row) for row in rows]
        tier_set = set(tiers)
        return [dict(row) for row in rows if int(row["tier"]) in tier_set]

    def _has_registered_embedding_function(self) -> bool:
        return "vector" in self._table.embedding_functions

    def _row_for_item(self, item: MemoryItem) -> dict[str, object]:
        row: dict[str, object] = {
            "id": item.id,
            "tier": item.tier,
            "text": item.text,
            "created_at": item.created_at,
        }
        if not self._has_registered_embedding_function():
            row["vector"] = self._source_embedding(item.text)
        return row

    def _source_embedding(self, text: str) -> list[float]:
        return _embedding_to_list(
            self._embedding_function.compute_source_embeddings_with_retry(text)[0]
        )

    def _query_embedding(self, text: str) -> list[float]:
        return _embedding_to_list(
            self._embedding_function.compute_query_embeddings_with_retry(text)[0]
        )


def _table_schema(function: EmbeddingFunction) -> pa.Schema:
    return pa.schema(
        [
            pa.field("id", pa.int64()),
            pa.field("tier", pa.int8()),
            pa.field("text", pa.string()),
            pa.field("created_at", pa.int64()),
            pa.field("vector", pa.list_(pa.float32(), function.ndims())),
        ]
    )


def _embedding_to_list(value: Any) -> list[float]:
    if value is None:  # pragma: no cover - defensive
        raise RuntimeError("embedding function returned null embedding")
    return [float(component) for component in list(value)]
