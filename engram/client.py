"""Public Engram client surface.

`EngramClient` is the thin programmatic adapter over the shared command layer,
analogous to Weft's `WeftClient`. It is suitable for application code and for
constructing read-only LLM tools.

Spec references:
- docs/specs/11-minimum-write-search-context-slice.md [MWS-12], [MWS-23], [MWS-27]
- docs/specs/12-local-app-surface.md [LAS-8], [LAS-12], [LAS-20], [LAS-29], [LAS-30]
- docs/specs/15-foundation-contracts-and-invariants.md [FCI-9], [FCI-13], [FCI-14]
"""

from __future__ import annotations

from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any

import llm

from engram._constants import (
    DEFAULT_CONTEXT_TOKENS,
    DEFAULT_IMPORTANCE,
    DEFAULT_SEARCH_LIMIT,
    RECALL_SCOPE_ITEM,
    normalize_recall_scope,
)
from engram._exceptions import EngramClosedError
from engram.commands import memory as commands

if TYPE_CHECKING:
    from engram.core.embeddings import EmbeddingModel
    from engram.core.memory import Engram


class EngramClient:
    """Thin client wrapper over Engram command operations."""

    def __init__(
        self,
        memory: Engram | None = None,
        *,
        path: str | Path | None = None,
        embedder: EmbeddingModel | None = None,
        submit_background: bool = True,
    ) -> None:
        if memory is not None and path is not None:
            raise ValueError("Pass either memory or path, not both")
        if memory is not None and embedder is not None:
            raise ValueError("Pass either memory or embedder, not both")
        self._closed = False
        self._memory = memory or commands.open_vault(
            path,
            embedder=embedder,
            submit_background=submit_background,
        )

    @classmethod
    def init(
        cls,
        path: str | Path | None = None,
        *,
        embedder: EmbeddingModel | None = None,
        autostart: bool = True,
        submit_background: bool = True,
    ) -> EngramClient:
        """Initialize a vault and return a client for it."""

        memory = commands.open_vault(
            path,
            create=True,
            embedder=embedder,
            autostart=autostart,
            submit_background=submit_background,
        )
        return cls(memory=memory)

    @classmethod
    def open(
        cls,
        path: str | Path | None = None,
        *,
        embedder: EmbeddingModel | None = None,
        submit_background: bool = True,
    ) -> EngramClient:
        """Open an existing vault and return a client for it."""

        memory = commands.open_vault(
            path,
            embedder=embedder,
            submit_background=submit_background,
        )
        return cls(memory=memory)

    @property
    def memory(self) -> Engram:
        """Return the wrapped low-level memory object."""

        self._require_open()
        return self._memory

    @property
    def vault_path(self) -> Path:
        """Return the wrapped vault path."""

        self._require_open()
        return self._memory.vault_path

    def __enter__(self) -> EngramClient:
        """Return this client for context-manager use."""

        self._require_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close this client when leaving a context manager."""

        del exc_type, exc, traceback
        self.close()

    def record(self, text: str, *, importance: int = DEFAULT_IMPORTANCE) -> int:
        """Store a memory moment and return its item ID."""

        self._require_open()
        return commands.record(self._memory, text, importance=importance)

    def set_importance(self, item_id: str | int, importance: int) -> dict[str, Any]:
        """Set a memory item's importance multiplier."""

        self._require_open()
        return commands.set_importance(
            self._memory,
            item_id,
            importance=importance,
        )

    def context(
        self,
        query: str | None = None,
        *,
        max_tokens: int = DEFAULT_CONTEXT_TOKENS,
    ) -> str:
        """Render assembled context for an optional query."""

        self._require_open()
        return commands.context(
            self._memory,
            term=query,
            total_tokens=max_tokens,
        )

    def search(
        self,
        query: str,
        *,
        limit: int = DEFAULT_SEARCH_LIMIT,
        count_access: bool = True,
    ) -> list[dict[str, Any]]:
        """Search memory and return JSON-serializable dictionaries."""

        self._require_open()
        return commands.search(
            self._memory,
            query,
            limit=limit,
            count_access=count_access,
        )

    def recall(
        self,
        item_id: str | int,
        *,
        scope: str | int = RECALL_SCOPE_ITEM,
        count_access: bool = True,
    ) -> dict[str, Any] | None:
        """Recall an item or containing summary by anchor ID.

        Omit the scope for exact item recall. Use `"episode"` or `1` for the
        containing episode, `"arc"` or `2` for the containing arc, or a higher
        integer tier such as `3` to recall the summary tier whose support
        contains the anchor.

        Examples:
            `client.recall(mid)`
            `client.recall(mid, scope="episode")`
            `client.recall(mid, scope=2)`
        """

        self._require_open()
        normalized_scope = normalize_recall_scope(scope)
        return commands.recall(
            self._memory,
            item_id,
            scope=normalized_scope,
            count_access=count_access,
        )

    def status(self) -> dict[str, Any]:
        """Return JSON-serializable vault status."""

        self._require_open()
        return commands.status(self._memory)

    def process(self, *, max_passes: int = 1000) -> dict[str, Any]:
        """Process locally repairable items until the vault is idle."""

        self._require_open()
        return commands.process(self._memory, max_passes=max_passes)

    def snapshot(self, output_path: str | Path) -> None:
        """Copy the processed vault directory to `output_path`."""

        self._require_open()
        commands.snapshot_vault(self._memory, output_path)

    def llm_tools(self) -> list[Any]:
        """Return read-only `llm` tools backed by this client.

        These tools intentionally do not increment access scores. Benchmark
        runs use frozen checkpoint vaults; the model-facing tool surface should
        not mutate those vaults.
        """

        self._require_open()

        def engram_context(
            query: str | None = None,
            max_tokens: int = 2048,
        ) -> str:
            return self.context(query=query, max_tokens=max_tokens)

        def engram_search(
            query: str,
            limit: int = 10,
        ) -> list[dict[str, Any]]:
            return self.search(query, limit=limit, count_access=False)

        def engram_recall(
            item_id: str,
            scope: str | int = RECALL_SCOPE_ITEM,
        ) -> dict[str, Any] | None:
            return self.recall(item_id, scope=scope, count_access=False)

        return [
            llm.Tool(
                name="engram_context",
                description="Return assembled Engram context for an optional query.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "max_tokens": {"type": "integer", "minimum": 1},
                    },
                },
                implementation=engram_context,
            ),
            llm.Tool(
                name="engram_search",
                description="Search Engram memory without mutating access scores.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "minLength": 1},
                        "limit": {"type": "integer", "minimum": 1},
                    },
                    "required": ["query"],
                },
                implementation=engram_search,
            ),
            llm.Tool(
                name="engram_recall",
                description=(
                    "Recall one Engram item or containing summary without "
                    "mutating access scores."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "item_id": {"type": "string", "minLength": 1},
                        "scope": {
                            "anyOf": [
                                {
                                    "type": "string",
                                    "enum": ["item", "episode", "arc"],
                                },
                                {
                                    "type": "integer",
                                    "minimum": 1,
                                },
                            ],
                            "default": RECALL_SCOPE_ITEM,
                        },
                    },
                    "required": ["item_id"],
                },
                implementation=engram_recall,
            ),
        ]

    def close(self) -> None:
        """Close open resources."""

        if self._closed:
            return
        try:
            self._memory.close()
        finally:
            self._closed = True

    def _require_open(self) -> None:
        """Raise a public lifecycle error if this client is closed."""

        if self._closed:
            raise EngramClosedError("EngramClient is closed")


__all__ = ["EngramClient"]
