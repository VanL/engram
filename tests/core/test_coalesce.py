from __future__ import annotations

from engram._models import MemoryItem
from engram.core.coalesce import choose_summary_window, summarize_arc, summarize_episode
from engram.core.memory import DeterministicEmbedder


def test_choose_summary_window_closes_on_semantic_boundary():
    embedder = DeterministicEmbedder(dimensions=32)
    items = [
        MemoryItem(id=1, tier=0, text="SQLite state store decision", created_at=1),
        MemoryItem(id=2, tier=0, text="SQLite vault migration notes", created_at=2),
        MemoryItem(id=3, tier=0, text="SQLite durability and retries", created_at=3),
        MemoryItem(
            id=4, tier=0, text="Dashboard colors and layout polish", created_at=4
        ),
    ]

    window = choose_summary_window(items, embed_text=embedder.embed_document)

    assert [item.id for item in window] == [1, 2, 3]


def test_summarize_episode_preserves_distinctive_terms():
    items = [
        MemoryItem(
            id=1, tier=0, text="Decision: use SQLite for the state store.", created_at=1
        ),
        MemoryItem(
            id=2, tier=0, text="Reason: LanceDB stays retrieval only.", created_at=2
        ),
        MemoryItem(id=3, tier=0, text="Rule: keep record non-blocking.", created_at=3),
    ]

    summary, terms = summarize_episode(items)

    assert "sqlite" in terms
    assert "lancedb" in terms
    assert "Key terms:" in summary


def test_summarize_arc_preserves_distinctive_terms():
    items = [
        MemoryItem(
            id=1,
            tier=1,
            text="Episode: Engram memory vault schema. Key terms: engram, memory, vault.",
            created_at=1,
        ),
        MemoryItem(
            id=2,
            tier=1,
            text="Episode: Engram memory index rebuild. Key terms: engram, memory, rebuild.",
            created_at=2,
        ),
        MemoryItem(
            id=3,
            tier=1,
            text="Episode: Engram memory context budget. Key terms: engram, memory, context.",
            created_at=3,
        ),
    ]

    summary, terms = summarize_arc(items)

    assert "engram" in terms
    assert "memory" in terms
    assert summary.startswith("Arc:")
