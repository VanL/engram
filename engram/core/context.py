"""Context assembly for Engram.

Spec references:
- docs/specs/11-minimum-write-search-context-slice.md [MWS-23], [MWS-24], [MWS-25], [MWS-26]
- docs/specs/13-context-assembly-and-arcs.md [CAA-5], [CAA-6], [CAA-7], [CAA-8]
"""

from __future__ import annotations

from collections.abc import Sequence

from engram._constants import (
    CONTEXT_BUDGET_IMMEDIATE,
    CONTEXT_BUDGET_LONG_TERM,
    CONTEXT_BUDGET_MEDIUM_TERM,
    CONTEXT_BUDGET_SHORT_TERM,
)
from engram._models import ContextSection, ContextView, MemoryItem, estimate_tokens


def resolve_budgets(
    *,
    total_tokens: int,
    immediate: float | None = None,
    short_term: float | None = None,
    medium_term: float | None = None,
    long_term: float | None = None,
) -> dict[str, int]:
    """Resolve token budgets across the four context horizons.

    Spec:
        - [CAA-5]
        - [CAA-6]
    """

    fractions = {
        "immediate": CONTEXT_BUDGET_IMMEDIATE if immediate is None else immediate,
        "short_term": CONTEXT_BUDGET_SHORT_TERM if short_term is None else short_term,
        "medium_term": CONTEXT_BUDGET_MEDIUM_TERM
        if medium_term is None
        else medium_term,
        "long_term": CONTEXT_BUDGET_LONG_TERM if long_term is None else long_term,
    }
    total_fraction = sum(fractions.values())
    if total_fraction <= 0.0:
        raise ValueError("context budget fractions must sum to a positive value")
    normalized = {name: value / total_fraction for name, value in fractions.items()}
    return {
        "immediate": int(total_tokens * normalized["immediate"]),
        "short_term": int(total_tokens * normalized["short_term"]),
        "medium_term": int(total_tokens * normalized["medium_term"]),
        "long_term": int(total_tokens * normalized["long_term"]),
    }


def select_items_for_budget(
    items: Sequence[MemoryItem],
    *,
    token_budget: int,
    exclude_ids: Sequence[int] = (),
) -> tuple[MemoryItem, ...]:
    """Select items in order until the token budget is exhausted."""
    selected: list[MemoryItem] = []
    remaining = token_budget
    excluded = set(exclude_ids)
    for item in items:
        if item.id in excluded:
            continue
        item_tokens = estimate_tokens(item.text)
        if item_tokens > remaining:
            continue
        selected.append(item)
        excluded.add(item.id)
        remaining -= item_tokens
    return tuple(selected)


def used_tokens(items: Sequence[MemoryItem]) -> int:
    """Return the estimated tokens used by the selected items."""
    return sum(estimate_tokens(item.text) for item in items)


def build_context_view(
    *,
    total_tokens: int,
    immediate_budget: int,
    short_budget: int,
    medium_budget: int,
    long_budget: int,
    immediate_items: Sequence[MemoryItem],
    short_items: Sequence[MemoryItem],
    medium_items: Sequence[MemoryItem],
    long_items: Sequence[MemoryItem],
) -> ContextView:
    """Assemble a multi-horizon context view."""
    sections = (
        ContextSection(
            name="immediate",
            token_budget=immediate_budget,
            items=tuple(immediate_items),
        ),
        ContextSection(
            name="short-term",
            token_budget=short_budget,
            items=tuple(short_items),
        ),
        ContextSection(
            name="medium-term",
            token_budget=medium_budget,
            items=tuple(medium_items),
        ),
        ContextSection(
            name="long-term",
            token_budget=long_budget,
            items=tuple(long_items),
        ),
    )
    return ContextView(total_tokens=total_tokens, sections=sections)
