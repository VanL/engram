from __future__ import annotations

VALIDATION_SCENARIOS = [
    {
        "name": "sqlite-state-store",
        "query": "Write notes about the SQLite state store for each vault.",
        "required_labels": ("decision_sqlite",),
        "history": [
            (
                "decision_sqlite",
                "Decision: use SQLite for the state store in each vault.",
            ),
            ("reason_lance", "Reason: keep LanceDB only for retrieval and search."),
            (
                "constraint_local",
                "Constraint: local vaults must stay self-contained and portable.",
            ),
            (
                "noise_ui",
                "UI thought: the dashboard should show failed item processing and retries.",
            ),
            (
                "noise_copy",
                "Docs thought: keep the README short and direct for agents.",
            ),
            (
                "noise_release",
                "Release thought: avoid new dependencies before the first slice ships.",
            ),
        ],
    },
    {
        "name": "deferred-write-path",
        "query": "Explain why record returns before indexing completes.",
        "required_labels": ("decision_async",),
        "history": [
            (
                "decision_async",
                "Decision: record returns after durable state write, before indexing.",
            ),
            (
                "reason_retry",
                "Reason: background work needs retry without losing the moment.",
            ),
            (
                "reason_queue",
                "Reason: SQLite stores processing state while Weft owns execution.",
            ),
            ("noise_docs", "Docs task: add a spec index entry for new product specs."),
            (
                "noise_style",
                "Style rule: keep plans executable for a zero-context engineer.",
            ),
            ("noise_naming", "Naming thought: use engram as the CLI root command."),
        ],
    },
    {
        "name": "context-does-not-boost",
        "query": "What was the rule about context assembly and access scoring?",
        "required_labels": ("decision_no_feedback",),
        "history": [
            (
                "decision_no_feedback",
                "Decision: context assembly must not increment access scores.",
            ),
            (
                "reason_feedback",
                "Reason: otherwise hot context items keep boosting themselves.",
            ),
            (
                "reason_explicit",
                "Rule: only explicit retrieval should increment access.",
            ),
            (
                "noise_tests",
                "Test task: keep real SQLite and LanceDB in integration tests.",
            ),
            (
                "noise_scope",
                "Scope note: defer blob ingestion until after the local app works.",
            ),
            (
                "noise_cli",
                "CLI thought: process is enough before a continuous worker exists.",
            ),
        ],
    },
    {
        "name": "episode-summary-roundtrip",
        "query": "Summarize the rule for episode summaries preserving distinctive terms.",
        "required_labels": ("decision_terms",),
        "history": [
            (
                "decision_terms",
                "Decision: episode summaries must preserve distinctive terms for retrieval.",
            ),
            (
                "reason_roundtrip",
                "Reason: summaries should act as cues back to original moments.",
            ),
            (
                "reason_search",
                "Reason: flat search still needs the original detail for drill-down.",
            ),
            (
                "noise_perf",
                "Perf note: skip premature vector index tuning in the first slice.",
            ),
            (
                "noise_release",
                "Release note: no Postgres support in the minimum skeleton.",
            ),
            (
                "noise_docs",
                "Docs note: update implementation notes when rationale changes.",
            ),
        ],
    },
]
