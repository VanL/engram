# Repository Map

Quick pointers to the key guidance documents and code in this repository.

## Root Entry Points

| Path | Purpose |
|------|---------|
| `AGENTS.md` | Canonical agent entry point |
| `CLAUDE.md` | Symlink to AGENTS.md |
| `README.md` | Project overview and design decisions |
| `bin/release.py` | Maintainer release helper for version sync, checks, commit, and tag push |
| `bin/build_github_pages_index.py` | Builds the GitHub Pages Python simple index from release assets |

## Package Structure

| Path | Purpose |
|------|---------|
| `engram/__init__.py` | Package entry, public API exports |
| `engram/_exceptions.py` | Shared Engram exceptions |
| `engram/_internal_tasks.py` | Code-owned internal Weft TaskSpec inventory |
| `engram/_models.py` | Shared Pydantic and dataclass models |
| `engram/_constants.py` | All constants, defaults, env var loading |
| `engram/cli.py` | CLI entry point |
| `engram/client.py` | Public app/tool client over shared commands |
| `engram/commands/` | Shared command layer for CLI, client, tools, and dogfood |
| `engram/runtime/weft.py` | Embedded Weft init and internal task submission |
| `engram/background.py` | Weft worker callback boundary |
| `engram/core/memory.py` | Main Engram API and background orchestration |
| `engram/core/coalesce.py` | Episode coalescing logic |
| `engram/core/context.py` | Context assembly helpers |
| `engram/core/embeddings.py` | Runtime and deterministic embedding providers |
| `engram/core/llm_tasks.py` | Gemini-backed structured summary extraction |
| `engram/core/scoring.py` | Retrieval scoring helpers |
| `engram/store/base.py` | State-store protocol consumed by the domain layer |
| `engram/store/sqlite.py` | Public SQLite state-store wrapper |
| `engram/store/core.py` | Backend-neutral state-store operations |
| `engram/store/db.py` | SQL runner, retry, transaction, and SQLite connection primitives |
| `engram/store/factory.py` | State-store backend selection boundary |
| `engram/store/id_generator.py` | Hybrid timestamp memory ID allocator |
| `engram/store/_sql/` | Backend SQL namespaces and ordered column contracts |
| `engram/store/backends/sqlite/` | SQLite runtime, validation, schema, and migration adapter |
| `engram/index/lance.py` | LanceDB retrieval wrapper |

## Shared Agent Context

| Path | Purpose |
|------|---------|
| `docs/agent-context/README.md` | Context hub and read order |
| `docs/agent-context/context.index.yaml` | Machine-readable context index |
| `docs/agent-context/decision-hierarchy.md` | Conflict-resolution order |
| `docs/agent-context/principles.md` | Shared execution principles |
| `docs/agent-context/engineering-principles.md` | Engineering rules for engram |

## Runbooks

| Path | Purpose |
|------|---------|
| `docs/agent-context/runbooks/writing-plans.md` | Plan-writing standard |
| `docs/agent-context/runbooks/hardening-plans.md` | Hardening checklist for risky plans |
| `docs/agent-context/runbooks/review-loops-and-agent-bootstrap.md` | Independent review workflow |
| `docs/agent-context/runbooks/writing-specs.md` | Spec-writing standard |
| `docs/agent-context/runbooks/writing-implementation-docs.md` | Implementation-doc standard |
| `docs/agent-context/runbooks/testing-patterns.md` | Testing and verification guidance |
| `docs/agent-context/runbooks/maintaining-traceability.md` | Documentation-maintenance gate |
| `docs/agent-context/runbooks/skills-lifecycle.md` | Skill promotion and maintenance |

## Core Documentation

| Path | Purpose |
|------|---------|
| `docs/specs/00-specs-index.md` | Numbered entry point for specs |
| `docs/specs/01-development-documentation-operating-model.md` | Governing spec for docs workflow |
| `docs/specs/10-minimum-memory-model.md` | Minimum Engram data model |
| `docs/specs/11-minimum-write-search-context-slice.md` | Minimum write/search/context behavior |
| `docs/specs/12-local-app-surface.md` | Local app lifecycle and recovery surface |
| `docs/specs/13-context-assembly-and-arcs.md` | Arc-tier context assembly behavior |
| `docs/specs/14-embedded-weft-execution-model.md` | Embedded Weft execution boundary |
| `docs/specs/15-foundation-contracts-and-invariants.md` | Layer, public surface, access, and CLI contract guardrails |
| `docs/plans/README.md` | Plan directory rules |
| `docs/implementation/00-implementation-index.md` | Numbered entry point for impl docs |
| `docs/implementation/01-documentation-system.md` | Why docs are shaped this way |
| `docs/implementation/03-agent-inventory.md` | Agent availability and review preference |
| `docs/implementation/04-minimum-memory-slice.md` | Current memory-slice rationale and boundaries |
| `docs/implementation/05-local-vault-recovery.md` | Vault lifecycle, migration, status, and rebuild rationale |
| `docs/implementation/06-arc-context-assembly.md` | Arc-tier context assembly rationale |
| `docs/implementation/07-codex-corpus-validation.md` | Codex corpus validation rationale |
| `tests/architecture/` | Executable import-boundary and private-access guardrails |
| `tests/system/test_release_script.py` | Release-helper and workflow structure tests |
| `tests/system/test_github_pages_index.py` | GitHub Pages simple-index generator tests |
| `docs/lessons.md` | Canonical lessons ledger |

## Project Configuration

| Path | Purpose |
|------|---------|
| `pyproject.toml` | Build config, dependencies, tool settings |
| `.github/workflows/test.yml` | Main CI test, lint, type-check, and coverage workflow |
| `.github/workflows/release-gate.yml` | Tag-driven release gate, GitHub Release artifact workflow, and Pages index deploy |
| `.github/workflows/release.yml` | Future PyPI publish workflow, intentionally disabled |
| `.envrc` | direnv/shell environment setup |
| `LICENSE` | MIT license |

## Skills

| Path | Purpose |
|------|---------|
| `skills/README.md` | Skill directory purpose and conventions |
| `skills/_template/SKILL.md` | Starter template for new skills |

## Update Guidance

When the repository grows:

- add new entry points and key modules here
- keep descriptions short and navigational
- when code modules are added, group them under a "Core Modules" section
  organized by responsibility (storage, retrieval, coalescing, context assembly)
