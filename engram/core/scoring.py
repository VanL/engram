"""Scoring helpers for Engram retrieval.

Spec references:
- docs/specs/10-minimum-memory-model.md [MM-18]
- docs/specs/11-minimum-write-search-context-slice.md [MWS-12], [MWS-21]
"""

from __future__ import annotations

from engram._constants import DEFAULT_RRF_K


def reciprocal_rank_fusion(rank: int, *, k: int = DEFAULT_RRF_K) -> float:
    """Return the Reciprocal Rank Fusion score for a rank position."""
    return 1.0 / float(k + rank)


def boosted_search_score(
    fused_score: float, *, access: float, relevance: float
) -> float:
    """Boost a fused retrieval score by Engram access state."""
    return fused_score * access * relevance
