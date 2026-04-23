from __future__ import annotations

from pathlib import Path

from engram.core.context import select_items_for_budget
from engram.core.memory import Engram
from tests.fixtures.state_inspection import children, recent_items
from tests.fixtures.validation_corpus import VALIDATION_SCENARIOS


def test_build_context_does_not_increment_access(memory):
    item_id = memory.record("Decision: only explicit retrieval increments access.")
    memory.process()

    before = memory.recall(item_id, count_access=False)
    memory.build_context(term="explicit retrieval", total_tokens=48)
    after = memory.recall(item_id, count_access=False)

    assert before.access == after.access


def test_context_uses_recent_and_long_term_items(memory):
    first = memory.record("Decision: use SQLite for the state store in each vault.")
    memory.record("Reason: keep LanceDB only for retrieval.")
    memory.record("Constraint: keep record non-blocking for callers.")
    memory.record("UI thought: show pending jobs in a status command.")
    memory.process()

    context = memory.build_context(term="SQLite state store", total_tokens=36)

    assert first in context.item_ids
    assert context.item_ids


def test_context_exposes_medium_term_arc_bucket(arc_memory):
    context = arc_memory.build_context(term="Engram memory", total_tokens=72)

    medium_section = next(
        section for section in context.sections if section.name == "medium-term"
    )

    assert medium_section.items
    assert all(item.is_arc for item in medium_section.items)


def test_sparse_corpus_keeps_empty_medium_term_bucket(memory):
    memory.record("Decision: keep sparse context assembly honest.")
    memory.process()

    context = memory.build_context(total_tokens=32)

    medium_section = next(
        section for section in context.sections if section.name == "medium-term"
    )
    assert medium_section.items == ()


def test_arc_summary_terms_round_trip_to_lower_tiers(arc_memory):
    arc_items = recent_items(arc_memory.vault_path, tier=2, limit=5)
    assert arc_items
    arc = arc_items[0]
    query = " ".join(arc.summary_terms[:2])

    results = arc_memory.search(query, limit=10)
    result_ids = {result.id for result in results}
    child_episodes = children(arc_memory.vault_path, arc.id)
    child_moment_ids: set[int] = set()
    for episode in child_episodes:
        child_moment_ids.update(
            item.id for item in children(arc_memory.vault_path, episode.id)
        )

    assert child_moment_ids & result_ids


def test_validation_corpus_beats_last_n(tmp_path: Path):
    engram_passes = 0
    last_n_failures = 0

    for scenario in VALIDATION_SCENARIOS:
        memory = Engram.init(tmp_path / scenario["name"])
        label_to_id = {}
        for label, text in scenario["history"]:
            label_to_id[label] = memory.record(text)
        memory.process()

        required_ids = {label_to_id[label] for label in scenario["required_labels"]}
        context = memory.build_context(term=scenario["query"], total_tokens=36)
        if required_ids.issubset(set(context.item_ids)):
            engram_passes += 1

        recent_moments = recent_items(memory.vault_path, tier=0, limit=50)
        baseline_items = select_items_for_budget(recent_moments, token_budget=36)
        baseline_ids = {item.id for item in baseline_items}
        if not required_ids.issubset(baseline_ids):
            last_n_failures += 1
        memory.close()

    assert engram_passes >= 3
    assert last_n_failures >= 2
