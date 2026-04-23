"""Shared Engram models.

Spec references:
- docs/specs/10-minimum-memory-model.md [MM-6], [MM-9], [MM-15]
- docs/specs/11-minimum-write-search-context-slice.md [MWS-9], [MWS-25]
- docs/specs/12-local-app-surface.md [LAS-8], [LAS-12]
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field, field_validator

from engram._constants import (
    DEFAULT_ACCESS_SCORE,
    DEFAULT_RELEVANCE_FLOOR,
    TIER_ARC,
    TIER_EPISODE,
    TIER_MOMENT,
)


class MemoryItem(BaseModel):
    """A durable memory item in a vault.

    Spec:
        - [MM-6]
        - [MM-9]
    """

    id: int = Field(..., ge=0, description="Shared Engram item ID")
    tier: int = Field(..., ge=0, description="Tier depth")
    text: str = Field(..., min_length=1, description="Stored text")
    created_at: int = Field(
        ...,
        description=(
            "Memory timeline timestamp in ns; moments use physical creation "
            "time and summaries use max child created_at"
        ),
    )
    access: float = Field(DEFAULT_ACCESS_SCORE, ge=0.0)
    relevance: float = Field(DEFAULT_RELEVANCE_FLOOR, ge=1.0)
    indexed_at: int | None = Field(None, description="Last index update in ns")
    summary_terms: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        """Reject empty or whitespace-only text."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("text must not be empty")
        return stripped

    @property
    def is_moment(self) -> bool:
        """Return whether this item is a moment."""
        return self.tier == TIER_MOMENT

    @property
    def is_episode(self) -> bool:
        """Return whether this item is an episode."""
        return self.tier == TIER_EPISODE

    @property
    def is_arc(self) -> bool:
        """Return whether this item is an arc."""
        return self.tier == TIER_ARC


class VaultStatus(BaseModel):
    """Structured vault and recovery status.

    Spec:
        - [LAS-8]
        - [LAS-9]
        - [LAS-10]
    """

    vault_path: str
    sqlite_path: str
    index_path: str
    broker_path: str
    schema_version: int = Field(..., ge=1)
    item_counts: dict[str, int] = Field(default_factory=dict)
    indexed_items: int = Field(..., ge=0)
    index_rows: int = Field(..., ge=0)
    items_needing_processing: int = Field(..., ge=0)
    unindexed_items: int = Field(..., ge=0)
    failed_processing_items: int = Field(..., ge=0)
    failed_items: tuple[FailedItemRecord, ...] = Field(default_factory=tuple)
    needs_rebuild: bool


class FailedItemRecord(BaseModel):
    """A recorded deferred-processing failure for one memory item.

    Spec:
        - [MWS-34]
        - [LAS-10]
        - [EWM-18]
    """

    id: int = Field(..., description="Shared Engram item ID")
    tier: int = Field(..., ge=0, description="Tier depth")
    text: str = Field(..., min_length=1, description="Stored text")
    created_at: int = Field(..., description="Creation timestamp in ns")
    indexed_at: int | None = Field(None, description="Last index update in ns")
    processing_attempts: int = Field(..., ge=0)
    error: str = Field(..., min_length=1)
    last_task_tid: str | None = None
    last_task_updated_at: int | None = Field(
        None,
        description="Last known Weft-correlation update timestamp in ns",
    )


class RebuildResult(BaseModel):
    """Structured result for one-way index rebuilds.

    Spec:
        - [LAS-12]
        - [LAS-13]
    """

    rebuilt_items: int = Field(..., ge=0)
    index_rows: int = Field(..., ge=0)
    indexed_at: int = Field(..., ge=0)


@dataclass(frozen=True, slots=True)
class SearchResult:
    """A ranked search result.

    Spec:
        - [MWS-12]
        - [MWS-21]
    """

    id: int
    tier: int
    text: str
    source: str
    fused_score: float
    access: float
    relevance: float
    score: float


@dataclass(frozen=True, slots=True)
class ProcessResult:
    """The result of local item processing."""

    processed_ids: tuple[int, ...]
    created_episode_ids: tuple[int, ...]
    failed_item_ids: tuple[int, ...]
    created_arc_ids: tuple[int, ...] = ()

    @property
    def processed_count(self) -> int:
        """Return the number of processed items."""
        return len(self.processed_ids)

    @property
    def is_idle(self) -> bool:
        """Return whether the local processing helper processed no items."""
        return (
            not self.processed_ids
            and not self.created_episode_ids
            and not self.created_arc_ids
        )


@dataclass(frozen=True, slots=True)
class ContextSection:
    """One assembled context bucket."""

    name: str
    token_budget: int
    items: tuple[MemoryItem, ...]


@dataclass(frozen=True, slots=True)
class ContextView:
    """A multi-horizon context view.

    Spec:
        - [MWS-23]
        - [MWS-25]
    """

    total_tokens: int
    sections: tuple[ContextSection, ...]

    @property
    def item_ids(self) -> tuple[int, ...]:
        """Return all selected item IDs in section order."""
        ids: list[int] = []
        for section in self.sections:
            ids.extend(item.id for item in section.items)
        return tuple(ids)

    def render(self) -> str:
        """Render the assembled context as plain text."""
        lines: list[str] = []
        for section in self.sections:
            if not section.items:
                continue
            lines.append(f"[{section.name}]")
            for item in section.items:
                lines.append(f"- {item.id} ({item.tier}): {item.text}")
            lines.append("")
        return "\n".join(lines).strip()

    def __str__(self) -> str:
        """Render as plain text."""
        return self.render()


def estimate_tokens(text: str) -> int:
    """Return a cheap token estimate for budgeting.

    This intentionally stays simple for the minimum slice.

    Spec:
        - [MWS-25]
    """

    words = len(text.split())
    if words == 0:
        return 0
    return max(1, words)
