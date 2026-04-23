"""LLM-backed summary extraction for higher-tier memory items.

Spec references:
- docs/specs/10-minimum-memory-model.md [MM-10], [MM-11], [MM-12]
- docs/specs/11-minimum-write-search-context-slice.md [MWS-16], [MWS-17]
- docs/specs/13-context-assembly-and-arcs.md [CAA-1], [CAA-4]
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any, Literal

import weft.core.agents  # noqa: F401
from pydantic import BaseModel, ConfigDict, Field
from weft.core.agents.runtime import (
    execute_agent_target,
)
from weft.core.taskspec import AgentSection

from engram._constants import (
    DEFAULT_SUMMARIZER_MODEL,
    SUMMARY_AGENT_MAX_OUTPUT_TOKENS,
    SUMMARY_AGENT_MAX_TURNS,
    SUMMARY_AGENT_TIMEOUT_SECONDS,
    TERM_EXTRACTION_TOP_K,
    TFIDF_MINIMUM_CORPUS_SIZE,
    TIER_ARC,
    TIER_EPISODE,
    tier_name,
)
from engram._models import MemoryItem

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
    "just",
    "keep",
    "more",
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
    "under",
    "use",
    "used",
    "using",
    "with",
    "would",
}
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_:-]{4,}")


class SummaryExtractionResult(BaseModel):
    """Structured output for LLM-backed summary extraction."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(
        ...,
        min_length=1,
        description=(
            "One concise 1-2 sentence summary body without a leading tier label."
        ),
    )
    keywords: list[str] = Field(
        default_factory=list,
        description=(
            "Five to eight distinctive lowercase retrieval cues grounded in the source."
        ),
    )


def summarize_items_with_llm(
    items: Sequence[MemoryItem],
    *,
    tier: int,
    corpus_items: Sequence[MemoryItem],
    model_name: str = DEFAULT_SUMMARIZER_MODEL,
) -> tuple[str, tuple[str, ...]]:
    """Return a formatted higher-tier summary and normalized keywords."""

    if not items:
        raise ValueError("cannot summarize an empty item window")

    supplemental_terms = select_tfidf_terms(
        items,
        corpus_items=corpus_items,
        limit=TERM_EXTRACTION_TOP_K,
    )
    payload = _run_summary_agent(
        items=items,
        tier=tier,
        supplemental_terms=supplemental_terms,
        model_name=model_name,
    )
    summary_body = payload.summary.strip().rstrip(".")
    keywords = normalize_keywords(
        payload.keywords,
        fallback_terms=supplemental_terms,
    )
    summary = f"{tier_name(tier).title()}: {summary_body}."
    if keywords:
        summary += " Key terms: " + ", ".join(keywords) + "."
    return summary, keywords


def select_tfidf_terms(
    items: Sequence[MemoryItem],
    *,
    corpus_items: Sequence[MemoryItem],
    limit: int,
) -> tuple[str, ...]:
    """Return a supplemental TF-IDF term set for the window.

    LanceDB's public Python surface exposes BM25-based search, not stable term
    statistics. Engram computes the equivalent corpus signal locally and keeps
    LanceDB as the retrieval owner.
    """

    if not items:
        return ()

    source_tier = items[0].tier
    tier_corpus = [item for item in corpus_items if item.tier == source_tier]
    if len(tier_corpus) < TFIDF_MINIMUM_CORPUS_SIZE:
        return ()

    document_frequencies: Counter[str] = Counter()
    for item in tier_corpus:
        document_frequencies.update(set(_tokenize(item.text)))

    if not document_frequencies:
        return ()

    term_frequencies = Counter[str]()
    first_seen: dict[str, int] = {}
    for position, item in enumerate(items):
        for token in _tokenize(item.text):
            term_frequencies[token] += 1
            first_seen.setdefault(token, position)

    corpus_size = len(tier_corpus)
    ranked = sorted(
        term_frequencies,
        key=lambda token: (
            -_tfidf_score(
                tf=term_frequencies[token],
                df=document_frequencies[token],
                corpus_size=corpus_size,
            ),
            first_seen[token],
            token,
        ),
    )
    return tuple(ranked[:limit])


def normalize_keywords(
    raw_keywords: Sequence[str] | None,
    *,
    fallback_terms: Sequence[str],
) -> tuple[str, ...]:
    """Normalize raw keyword output to a stable stored form."""

    normalized: list[str] = []
    seen: set[str] = set()
    for value in raw_keywords or ():
        candidate = value.strip().lower()
        candidate = re.sub(r"\s+", " ", candidate)
        if not candidate or candidate in seen:
            continue
        if candidate in STOPWORDS:
            continue
        normalized.append(candidate)
        seen.add(candidate)
        if len(normalized) >= TERM_EXTRACTION_TOP_K:
            return tuple(normalized)

    for value in fallback_terms:
        candidate = value.strip().lower()
        if not candidate or candidate in seen:
            continue
        normalized.append(candidate)
        seen.add(candidate)
        if len(normalized) >= TERM_EXTRACTION_TOP_K:
            break
    return tuple(normalized)


def _run_summary_agent(
    *,
    items: Sequence[MemoryItem],
    tier: int,
    supplemental_terms: Sequence[str],
    model_name: str,
) -> SummaryExtractionResult:
    output_mode = _summary_output_mode(model_name)
    agent_payload: dict[str, Any] = {
        "runtime": "llm",
        "authority_class": "bounded",
        "model": model_name,
        "instructions": _system_prompt(tier=tier),
        "output_mode": output_mode,
        "max_turns": SUMMARY_AGENT_MAX_TURNS,
        "options": {
            "temperature": 0.0,
            "thinking_level": "minimal",
            "json_object": True,
            "timeout": SUMMARY_AGENT_TIMEOUT_SECONDS,
            "max_output_tokens": SUMMARY_AGENT_MAX_OUTPUT_TOKENS,
        },
    }
    if output_mode == "json":
        agent_payload["output_schema"] = "engram.core.llm_tasks:SummaryExtractionResult"
    agent = AgentSection.model_validate(agent_payload)
    result = execute_agent_target(
        agent,
        _render_prompt(items=items, tier=tier, supplemental_terms=supplemental_terms),
    )
    payload = result.aggregate_public_output()
    if isinstance(payload, Mapping):
        normalized = _normalize_summary_payload(payload)
    else:
        text_payload = _public_text_output(payload)
        if text_payload is None:
            raise RuntimeError("summary agent did not return a parseable payload")
        parsed_payload = _json_object_from_text(text_payload)
        if parsed_payload is None:
            raise RuntimeError("summary agent returned non-JSON text")
        normalized = parsed_payload
    return SummaryExtractionResult.model_validate(dict(normalized))


def _summary_output_mode(model_name: str) -> Literal["json", "text"]:
    """Return the Weft output mode that preserves content for the model."""

    if model_name.startswith("gemini/"):
        return "text"
    return "json"


def _public_text_output(payload: Any) -> str | None:
    """Return text from Weft public output shapes."""

    if isinstance(payload, str):
        return payload
    if isinstance(payload, Sequence) and not isinstance(payload, str):
        if len(payload) != 1:
            return None
        value = payload[0]
        if isinstance(value, str):
            return value
    return None


def _normalize_summary_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return a schema-shaped summary payload from provider-specific output."""

    if "summary" in payload:
        return payload
    gemini_text = _extract_gemini_candidate_text(payload)
    if gemini_text is None:
        return payload
    parsed = _json_object_from_text(gemini_text)
    if parsed is None:
        return payload
    return parsed


def _extract_gemini_candidate_text(payload: Mapping[str, Any]) -> str | None:
    """Extract text from a raw Gemini response envelope when present."""

    candidates = payload.get("candidates")
    if isinstance(candidates, str) or not isinstance(candidates, Sequence):
        return None
    if not candidates:
        return None
    candidate = candidates[0]
    if not isinstance(candidate, Mapping):
        return None
    content = candidate.get("content")
    if not isinstance(content, Mapping):
        return None
    parts = content.get("parts")
    if isinstance(parts, str) or not isinstance(parts, Sequence):
        return None

    texts: list[str] = []
    for part in parts:
        if not isinstance(part, Mapping):
            continue
        text = part.get("text")
        if isinstance(text, str) and text.strip():
            texts.append(text.strip())
    if not texts:
        return None
    return "\n".join(texts)


def _json_object_from_text(text: str) -> Mapping[str, Any] | None:
    """Parse a JSON object from plain or fenced model text."""

    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        parsed = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, Mapping):
        return None
    return parsed


def _system_prompt(*, tier: int) -> str:
    label = tier_name(tier)
    parent = {
        TIER_EPISODE: "ordered moment",
        TIER_ARC: "ordered episode",
    }.get(tier, "ordered memory")
    return (
        "You compress Engram memory windows into higher-tier summaries.\n"
        f"You are producing a tier-{label} summary over {parent} items.\n"
        "Rules:\n"
        "- Preserve distinctive names, file paths, APIs, products, and error strings.\n"
        "- Keep the summary factual and compact.\n"
        "- Do not invent facts or keywords.\n"
        "- Prefer supplied candidate terms when they are supported by the source.\n"
        "- Return a JSON object with exactly these fields: summary, keywords."
    )


def _render_prompt(
    *,
    items: Sequence[MemoryItem],
    tier: int,
    supplemental_terms: Sequence[str],
) -> str:
    lines = [
        f"Target tier: {tier_name(tier)}",
        f"Source item count: {len(items)}",
    ]
    if supplemental_terms:
        lines.append("Candidate TF-IDF terms: " + ", ".join(supplemental_terms))
    else:
        lines.append("Candidate TF-IDF terms: none")
    lines.append("")
    lines.append("Ordered source items:")
    for index, item in enumerate(items, start=1):
        lines.append(f"{index}. {item.text}")
    return "\n".join(lines)


def _tokenize(text: str) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for token in TOKEN_PATTERN.findall(text):
        normalized = token.lower()
        if normalized in STOPWORDS:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return tuple(ordered)


def _tfidf_score(*, tf: int, df: int, corpus_size: int) -> float:
    return float(tf) * (math.log((1 + corpus_size) / (1 + df)) + 1.0)


__all__ = [
    "SummaryExtractionResult",
    "normalize_keywords",
    "select_tfidf_terms",
    "summarize_items_with_llm",
]
