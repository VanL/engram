from __future__ import annotations

from engram.core.scoring import boosted_search_score, reciprocal_rank_fusion


def test_reciprocal_rank_fusion_prefers_higher_rank():
    first = reciprocal_rank_fusion(1)
    second = reciprocal_rank_fusion(2)

    assert first > second


def test_boosted_search_score_uses_access_and_relevance_multiplicatively():
    assert boosted_search_score(0.5, access=2.0, relevance=3.0) == 3.0
