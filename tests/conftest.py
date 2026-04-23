from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from engram._constants import TIER_ARC, TIER_EPISODE, tier_name
from engram.core.coalesce import (
    summarize_arc,
    summarize_episode,
    summarize_summary_items,
)
from engram.core.embeddings import DeterministicEmbedder
from engram.core.memory import Engram
from tests.fixtures.resource_cleanup import (
    ResourceTracker,
    ensure_windows_cleanup,
)


@pytest.fixture
def vault_path(tmp_path: Path) -> Path:
    return tmp_path / ".engram"


@pytest.fixture(autouse=True)
def local_runtime_shims(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "engram.core.memory.Engram._submit_background_task",
        lambda self, item_id: None,
    )
    monkeypatch.setattr(
        "engram.core.memory.SentenceTransformerEmbedder",
        DeterministicEmbedder,
    )

    def _fake_summarize(
        items,
        *,
        tier,
        corpus_items,
        model_name="unused",
    ):
        del corpus_items, model_name
        if tier == TIER_EPISODE:
            return summarize_episode(items)
        if tier == TIER_ARC:
            return summarize_arc(items)
        return summarize_summary_items(
            items,
            label=tier_name(tier).title(),
            remainder_label=f"{tier_name(tier - 1)}s",
        )

    monkeypatch.setattr(
        "engram.core.memory.summarize_items_with_llm",
        _fake_summarize,
    )


@pytest.fixture
def resource_tracker() -> Iterator[ResourceTracker]:
    tracker = ResourceTracker()
    try:
        yield tracker
    finally:
        tracker.close_all()
        ensure_windows_cleanup()


@pytest.fixture
def memory(vault_path: Path, resource_tracker: ResourceTracker) -> Iterator[Engram]:
    instance = resource_tracker.register(
        Engram.init(vault_path, embedder=DeterministicEmbedder())
    )
    yield instance


ARC_HISTORY = (
    "Engram memory vault schema metadata decision.",
    "Engram memory vault schema version rollout.",
    "Engram memory vault metadata recovery plan.",
    "Engram memory index rebuild decision.",
    "Engram memory Lance search rebuild notes.",
    "Engram memory hybrid retrieval repair plan.",
    "Engram memory context budget decision.",
    "Engram memory context medium-term bucket notes.",
    "Engram memory high-importance long-term context rule.",
    "Marketing poster typography direction.",
    "Marketing poster color palette review.",
    "Marketing poster launch headline copy.",
    "Accounting receipt export reconciliation.",
)


@pytest.fixture
def arc_memory(memory: Engram) -> Engram:
    for text in ARC_HISTORY:
        memory.record(text)
    memory.process()
    return memory
