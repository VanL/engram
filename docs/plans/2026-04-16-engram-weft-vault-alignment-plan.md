## Goal

Make Engram's Weft-backed background runtime use the Engram vault directory as
its Weft metadata directory so Engram-owned Weft state lands inside the vault
instead of colliding with an ordinary project `.weft` directory.

## Source Documents

Source specs:
- `docs/specs/10-minimum-memory-model.md` [MM-1], [MM-2]
- `docs/specs/11-minimum-write-search-context-slice.md` [MWS-5], [MWS-6], [MWS-9]
- `docs/specs/12-local-app-surface.md` [LAS-18], [LAS-19]

Source guidance:
- `AGENTS.md`
- `docs/agent-context/principles.md`
- `docs/agent-context/engineering-principles.md`
- `docs/agent-context/runbooks/testing-patterns.md`

## Context and Key Files

Files to modify:
- `engram/background.py`
- `tests/` background-focused regression coverage
- minimal docs that describe the Weft integration boundary

Files to read first:
- `engram/background.py`
- `engram/core/memory.py`
- `docs/specs/11-minimum-write-search-context-slice.md`
- `docs/implementation/04-minimum-memory-slice.md`

Cross-repo dependency:
- `../weft/weft/context.py`
- `../weft/weft/_constants.py`

Current structure:
- Engram stores its own vault data under `.engram/`
- Engram background submission currently passes the vault path as
  `weft_context`, which makes Weft treat the vault as the project root
- Weft needs an in-process config seam so an embedding app can override the
  Weft metadata-directory name without mutating global env

## Invariants and Constraints

- Weft remains the only background execution substrate
- Engram does not introduce a second durable task queue
- `TaskSpec.spec.weft_context` remains a project root, not a combined
  root-plus-directory-name path
- A vault remains an isolated namespace. Engram-owned Weft state must land
  inside the vault directory for the default sqlite-backed case
- Keep the change local. Do not redesign Engram vault layout or Weft bootstrap
  ownership beyond the explicit config seam

## Tasks

1. Add the Weft config seam.
   - Add an optional loaded-config argument to `build_context()` so embedded
     apps can override Weft-owned discovery inputs in-process.
   - Cover it with a targeted Weft context test.

2. Align Engram background submission to the vault boundary.
   - Derive `project_root = vault_path.parent`
   - Derive `weft_directory_name = vault_path.name`
   - Build a Weft config override from Engram-owned env names
   - Use plain `ENGRAM_*` names where possible and reserve `ENGRAM_WEFT_*`
     only for conflicts with Engram's own app-level env surface
   - Keep the vault path authoritative for the embedded Weft directory name and
     default sqlite broker path, even if matching Engram env overrides are set
   - Pass `project_root` into Weft context discovery and task `weft_context`
   - Keep the real `vault_path` only in the Engram task payload

3. Prove the contract with focused tests.
   - Engram background submission should produce a Weft context whose root is
     the vault parent and whose metadata directory is the vault path itself
   - The submitted TaskSpec should carry the parent root in `weft_context`

4. Update the minimal docs.
   - Record that Engram-owned Weft state lives inside the vault directory for
     the default sqlite-backed local path
