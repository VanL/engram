from __future__ import annotations

import time

from engram._models import MemoryItem
from engram.core.embeddings import DeterministicLanceEmbeddings
from engram.index.lance import LanceIndex


def test_lance_index_supports_text_and_vector_search(vault_path):
    index = LanceIndex(
        vault_path,
        embedding_function=DeterministicLanceEmbeddings.create(
            dimensions=8,
            max_retries=0,
        ),
    )
    first = MemoryItem(
        id=time.time_ns(),
        tier=0,
        text="SQLite keeps transactional state in the vault.",
        created_at=time.time_ns(),
    )
    second = MemoryItem(
        id=time.time_ns() + 1,
        tier=0,
        text="LanceDB handles retrieval and search.",
        created_at=time.time_ns() + 1,
    )
    try:
        index.upsert_item(first)
        index.upsert_item(second)

        text_rows = index.search_text("SQLite", limit=5)
        vector_rows = index.search_vector("SQLite transactional vault state", limit=5)
    finally:
        index.close()

    assert text_rows[0]["id"] == first.id
    assert vector_rows[0]["id"] == first.id
