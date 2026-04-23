"""Embedding implementations for Engram retrieval and coalescing.

Spec references:
- docs/specs/11-minimum-write-search-context-slice.md [MWS-10], [MWS-11], [MWS-14]
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

import numpy as np
from lancedb.embeddings import get_registry  # type: ignore[import-untyped]
from lancedb.embeddings.base import (  # type: ignore[import-untyped]
    EmbeddingFunction,
    TextEmbeddingFunction,
)

from engram._constants import (
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_EMBEDDING_MODEL,
)

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_:-]+")
_REGISTRY = get_registry()


class EmbeddingModel(Protocol):
    """Stable embedding interface used by Engram coalescing."""

    def embed_document(self, text: str) -> list[float]:
        """Embed stored text for coalescing."""

    def embed_query(self, text: str) -> list[float]:
        """Embed query text."""


class LanceEmbeddingModel:
    """Adapter exposing a Lance embedding function through Engram's interface."""

    def __init__(self, lance_function: EmbeddingFunction) -> None:
        self._lance_function = lance_function

    @property
    def lance_function(self) -> EmbeddingFunction:
        """Return the underlying Lance embedding function."""
        return self._lance_function

    def embed_document(self, text: str) -> list[float]:
        """Embed stored text with the underlying Lance function."""
        return _embedding_to_list(
            self._lance_function.compute_source_embeddings_with_retry(text)[0]
        )

    def embed_query(self, text: str) -> list[float]:
        """Embed query text with the underlying Lance function."""
        return _embedding_to_list(
            self._lance_function.compute_query_embeddings_with_retry(text)[0]
        )


@_REGISTRY.register("engram-deterministic")
class DeterministicLanceEmbeddings(TextEmbeddingFunction):
    """Small local embedding function for tests and offline fallbacks."""

    dimensions: int = DEFAULT_EMBEDDING_DIM

    def ndims(self) -> int:
        """Return the configured embedding dimensionality."""
        return self.dimensions

    def generate_embeddings(
        self,
        texts: list[str] | np.ndarray,
        *args: object,
        **kwargs: object,
    ) -> list[np.ndarray]:
        """Generate deterministic embeddings for one or more texts."""
        del args, kwargs
        return [np.array(self._embed(str(text)), dtype=np.float32) for text in texts]

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = TOKEN_PATTERN.findall(text.lower())
        if not tokens:
            return vector
        for token in tokens:
            digest = hashlib.blake2b(
                token.encode("utf-8"),
                digest_size=16,
            ).digest()
            for offset in (0, 4):
                index = (
                    int.from_bytes(digest[offset : offset + 4], "big") % self.dimensions
                )
                sign = 1.0 if digest[offset + 1] % 2 == 0 else -1.0
                vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]


class DeterministicEmbedder(LanceEmbeddingModel):
    """Deterministic embedder adapter backed by a Lance embedding function."""

    def __init__(self, *, dimensions: int = DEFAULT_EMBEDDING_DIM) -> None:
        super().__init__(
            DeterministicLanceEmbeddings.create(
                dimensions=dimensions,
                max_retries=0,
            )
        )


class SentenceTransformerEmbedder(LanceEmbeddingModel):
    """Production embedder backed by Lance's sentence-transformers integration."""

    def __init__(self, *, model_name: str = DEFAULT_EMBEDDING_MODEL) -> None:
        super().__init__(default_lance_embedding_function(model_name=model_name))


def default_lance_embedding_function(
    *,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
) -> EmbeddingFunction:
    """Return the default Lance embedding function for dense retrieval."""

    normalized_name = _normalize_sentence_transformer_name(model_name)
    embedding_cls = _REGISTRY.get("sentence-transformers")
    return embedding_cls.create(
        name=normalized_name,
        normalize=True,
        trust_remote_code="nomic" in normalized_name.lower(),
    )


def embedder_to_lance_function(embedder: EmbeddingModel) -> EmbeddingFunction:
    """Return the Lance embedding function backing an Engram embedder."""

    lance_function = getattr(embedder, "lance_function", None)
    if isinstance(lance_function, EmbeddingFunction):
        return lance_function
    raise TypeError(
        "Engram embedder must expose a Lance embedding function via 'lance_function'"
    )


def _normalize_sentence_transformer_name(model_name: str) -> str:
    if model_name.startswith("sentence-transformers/"):
        return model_name.split("/", maxsplit=1)[1]
    return model_name


def _embedding_to_list(value: np.ndarray | list[float] | None) -> list[float]:
    if value is None:  # pragma: no cover - defensive
        raise RuntimeError("embedding function returned null embedding")
    if isinstance(value, np.ndarray):
        return [float(component) for component in value.tolist()]
    return [float(component) for component in value]


__all__ = [
    "DeterministicEmbedder",
    "DeterministicLanceEmbeddings",
    "EmbeddingModel",
    "LanceEmbeddingModel",
    "SentenceTransformerEmbedder",
    "default_lance_embedding_function",
    "embedder_to_lance_function",
]
