# Weft Background And LLM Integration Plan

Date: 2026-04-16
Status: Completed

## Source Specs

- `docs/specs/11-minimum-write-search-context-slice.md` [MWS-1], [MWS-5],
  [MWS-10], [MWS-16], [MWS-27]
- `docs/specs/12-local-app-surface.md` [LAS-8], [LAS-9], [LAS-17], [LAS-20]
- `docs/specs/13-context-assembly-and-arcs.md` [CAA-1], [CAA-5], [CAA-11]

## Requested Outcomes

- Replace the placeholder NLP path with real model-backed summarization and
  keyword extraction.
- Use `gemini/gemini-3.1-flash-lite-preview` for structured coalescing output.
- Use Weft for background execution instead of an Engram-owned queue.
- Keep Engram's own SQLite database authoritative for memory state.

## Invariants

- SQLite remains the source of truth.
- LanceDB remains rebuildable.
- Weft owns execution and queueing.
- Engram records item-processing state only. No second durable queue.
- Tests stay deterministic by mocking only the external model and task
  boundary.

## Tasks

1. Add runtime embedding and LLM summary providers.
2. Add a Weft-backed submission path and worker entry point.
3. Remove queue-shaped Engram storage and status abstractions.
4. Update CLI, API, tests, specs, and implementation notes.
5. Verify with `pytest`, `mypy`, and `ruff`.

## Notes

- LanceDB's public Python API does not expose stable TF-IDF or term-stat
  surfaces. Supplemental corpus weighting is therefore computed locally rather
  than by depending on undocumented Lance internals.
- The local `work` helper remains as repair and test tooling. It is not the
  primary background path and it does not imply an Engram queue.
