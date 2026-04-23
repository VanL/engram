from __future__ import annotations

from typing import Any

from engram._constants import SUMMARY_AGENT_MAX_TURNS, TIER_EPISODE
from engram._models import MemoryItem
from engram.core.llm_tasks import summarize_items_with_llm


class _FakeAgentResult:
    def aggregate_public_output(self) -> dict[str, Any]:
        return {
            "summary": "A compact test summary",
            "keywords": ["alpha", "beta"],
        }


def test_summary_agent_uses_chain_limit_that_allows_one_response(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_execute_agent_target(agent, prompt):
        captured["max_turns"] = agent.max_turns
        captured["output_mode"] = agent.output_mode
        captured["prompt"] = prompt
        return _FakeAgentResult()

    monkeypatch.setattr(
        "engram.core.llm_tasks.execute_agent_target",
        fake_execute_agent_target,
    )

    item = MemoryItem(
        id=1,
        tier=0,
        text="Alpha beta source memory.",
        created_at=1,
    )
    summary, keywords = summarize_items_with_llm(
        [item],
        tier=TIER_EPISODE,
        corpus_items=[item],
    )

    assert captured["max_turns"] == SUMMARY_AGENT_MAX_TURNS
    assert captured["max_turns"] >= 2
    assert captured["output_mode"] == "text"
    assert summary == "Episode: A compact test summary. Key terms: alpha, beta."
    assert keywords == ("alpha", "beta")


def test_summary_agent_unwraps_raw_gemini_response_envelope(monkeypatch) -> None:
    class GeminiEnvelopeResult:
        def aggregate_public_output(self) -> dict[str, Any]:
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        '{"summary": "Gemini envelope summary", '
                                        '"keywords": ["gemini", "schema"]}'
                                    )
                                }
                            ]
                        },
                        "finishReason": "STOP",
                        "index": 0,
                    }
                ],
                "modelVersion": "gemini-3.1-flash-lite-preview",
            }

    monkeypatch.setattr(
        "engram.core.llm_tasks.execute_agent_target",
        lambda agent, prompt: GeminiEnvelopeResult(),
    )

    item = MemoryItem(
        id=1,
        tier=0,
        text="Gemini schema response source memory.",
        created_at=1,
    )
    summary, keywords = summarize_items_with_llm(
        [item],
        tier=TIER_EPISODE,
        corpus_items=[item],
    )

    assert summary == "Episode: Gemini envelope summary. Key terms: gemini, schema."
    assert keywords == ("gemini", "schema")


def test_summary_agent_parses_gemini_text_mode_json(monkeypatch) -> None:
    class GeminiTextResult:
        def aggregate_public_output(self) -> tuple[str]:
            return ('{"summary": "Text mode summary", "keywords": ["text", "json"]}',)

    monkeypatch.setattr(
        "engram.core.llm_tasks.execute_agent_target",
        lambda agent, prompt: GeminiTextResult(),
    )

    item = MemoryItem(
        id=1,
        tier=0,
        text="Text mode Gemini response source memory.",
        created_at=1,
    )
    summary, keywords = summarize_items_with_llm(
        [item],
        tier=TIER_EPISODE,
        corpus_items=[item],
    )

    assert summary == "Episode: Text mode summary. Key terms: text, json."
    assert keywords == ("text", "json")
