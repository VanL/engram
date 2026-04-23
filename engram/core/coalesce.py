"""Summary-tier coalescing for Engram.

Spec references:
- docs/specs/10-minimum-memory-model.md [MM-10], [MM-11], [MM-12]
- docs/specs/11-minimum-write-search-context-slice.md [MWS-13], [MWS-14], [MWS-16]
- docs/specs/13-context-assembly-and-arcs.md [CAA-1], [CAA-2], [CAA-4]
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence

from engram._constants import (
    COALESCE_MAX_WINDOW,
    COALESCE_MIN_WINDOW,
    COALESCE_SIMILARITY_THRESHOLD,
    TERM_EXTRACTION_TOP_K,
)
from engram._models import MemoryItem

EmbeddingFn = Callable[[str], Sequence[float]]

STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "been",
    "being",
    "build",
    "could",
    "from",
    "have",
    "into",
    "need",
    "only",
    "over",
    "same",
    "than",
    "that",
    "their",
    "there",
    "they",
    "this",
    "those",
    "through",
    "use",
    "with",
    "would",
}

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_:-]{4,}")


def choose_episode_window(
    items: Sequence[MemoryItem],
    *,
    embed_text: EmbeddingFn,
    min_window: int = COALESCE_MIN_WINDOW,
    max_window: int = COALESCE_MAX_WINDOW,
    threshold: float = COALESCE_SIMILARITY_THRESHOLD,
) -> tuple[MemoryItem, ...]:
    """Choose the next closable episode window.

    Returns an empty tuple when the available ordered moments do not yet form a
    closable semantic window.

    Spec:
        - [MWS-14]
        - [MWS-15]
    """
    return choose_summary_window(
        items,
        embed_text=embed_text,
        min_window=min_window,
        max_window=max_window,
        threshold=threshold,
    )


def choose_arc_window(
    items: Sequence[MemoryItem],
    *,
    embed_text: EmbeddingFn,
    min_window: int = COALESCE_MIN_WINDOW,
    max_window: int = COALESCE_MAX_WINDOW,
    threshold: float = COALESCE_SIMILARITY_THRESHOLD,
) -> tuple[MemoryItem, ...]:
    """Choose the next closable arc window.

    Spec:
        - [CAA-1]
        - [CAA-2]
    """
    return choose_summary_window(
        items,
        embed_text=embed_text,
        min_window=min_window,
        max_window=max_window,
        threshold=threshold,
    )


def choose_summary_window(
    items: Sequence[MemoryItem],
    *,
    embed_text: EmbeddingFn,
    min_window: int = COALESCE_MIN_WINDOW,
    max_window: int = COALESCE_MAX_WINDOW,
    threshold: float = COALESCE_SIMILARITY_THRESHOLD,
) -> tuple[MemoryItem, ...]:
    """Choose the next closable semantic summary window."""

    if len(items) <= min_window and len(items) < max_window:
        return ()

    window = list(items[:min_window])
    vectors = [list(embed_text(item.text)) for item in window]
    if len(items) == min_window:
        return ()

    for item in items[min_window:]:
        next_vector = list(embed_text(item.text))
        similarity = cosine_similarity(next_vector, centroid(vectors))
        if similarity < threshold:
            return tuple(window)
        window.append(item)
        vectors.append(next_vector)
        if len(window) >= max_window:
            return tuple(window)
    return ()


def summarize_episode(items: Sequence[MemoryItem]) -> tuple[str, tuple[str, ...]]:
    """Create a compact, cue-preserving episode summary.

    Spec:
        - [MM-11]
        - [MWS-16]
    """
    return summarize_summary_items(
        items,
        label="Episode",
        remainder_label="moments",
    )


def summarize_arc(items: Sequence[MemoryItem]) -> tuple[str, tuple[str, ...]]:
    """Create a compact, cue-preserving arc summary.

    Spec:
        - [CAA-1]
        - [CAA-4]
    """
    terms = extract_distinctive_terms(items, limit=TERM_EXTRACTION_TOP_K)
    if terms:
        summary = "Arc: " + ", ".join(terms[:6])
    else:
        summary = "Arc: " + " | ".join(
            normalize_summary_fragment(item.text) for item in items[:2]
        )
    summary += f" ({len(items)} episodes)"
    return summary, terms


def summarize_summary_items(
    items: Sequence[MemoryItem],
    *,
    label: str,
    remainder_label: str,
) -> tuple[str, tuple[str, ...]]:
    """Create a compact summary for an ordered semantic window."""

    lead_fragments: list[str] = []
    for item in items[:2]:
        fragment = normalize_summary_fragment(item.text)
        lead_fragments.append(fragment)
    summary = f"{label}: " + " | ".join(lead_fragments)
    if len(items) > 2:
        summary += f" (+{len(items) - 2} more {remainder_label})"
    terms = extract_distinctive_terms(items, limit=TERM_EXTRACTION_TOP_K)
    if terms:
        summary += ". Key terms: " + ", ".join(terms) + "."
    else:
        summary += "."
    return summary, terms


def normalize_summary_fragment(text: str) -> str:
    """Return a concise fragment suitable for higher-tier summaries."""
    fragment = text.strip()
    if ". Key terms:" in fragment:
        fragment = fragment.split(". Key terms:", 1)[0]
    if ": " in fragment:
        prefix, remainder = fragment.split(": ", 1)
        if prefix in {"Episode", "Arc"}:
            fragment = remainder
    return fragment.rstrip(".")


def extract_distinctive_terms(
    items: Sequence[MemoryItem],
    *,
    limit: int = TERM_EXTRACTION_TOP_K,
) -> tuple[str, ...]:
    """Extract stable retrieval cues from a set of items."""

    ordered_terms: list[str] = []
    seen: set[str] = set()
    for item in items:
        for token in TOKEN_PATTERN.findall(item.text):
            normalized = token.lower()
            if normalized in STOPWORDS:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            ordered_terms.append(normalized)
            if len(ordered_terms) >= limit:
                return tuple(ordered_terms)
    return tuple(ordered_terms)


def centroid(vectors: Sequence[Sequence[float]]) -> list[float]:
    """Return the centroid of a set of vectors."""
    if not vectors:
        return []
    length = len(vectors[0])
    sums = [0.0] * length
    for vector in vectors:
        for index, value in enumerate(vector):
            sums[index] += float(value)
    count = float(len(vectors))
    return [value / count for value in sums]


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Return cosine similarity between two vectors."""
    if not left or not right:
        return 0.0
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for left_value, right_value in zip(left, right, strict=False):
        dot += float(left_value) * float(right_value)
        left_norm += float(left_value) * float(left_value)
        right_norm += float(right_value) * float(right_value)
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (math.sqrt(left_norm) * math.sqrt(right_norm))
