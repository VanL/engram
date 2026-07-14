# Agent-Guidance Propagation Plan (2026-07-14 wave)

Status: Active
Class: 5+P — normative spec sections land in the spec tree ([DOM-14],
[DOM-15]); [DOM-6]-material to future process. Hardening: N/A — no
[DOM-5] risky trigger (docs and guidance only).
Source: agent-guidance @ `2f7eff6`; source content carried seven review
rounds there plus taut and backstitch adaptation reviews (grok). This
repo's review is scoped to the adaptation.

## 1. Goal and Scope

Adopt the 2026-07-14 wave (coalescing layer, task classification,
review lens, crosswalk, four skills) AND land the previously uncommitted
2026-07-02 verification-lessons fold in the same change, closing both
provenance debts (fold → `5927481`; wave → `2f7eff6`). The dirty
worktree at adoption time was exactly that fold (11 guidance files +
the probes runbook); no code WIP exists, so one combined landing is
clean and mirrors how agent-guidance itself landed its wave.

## 2. Invariants and Adaptations

- **Section-number remap:** this repo's engineering-principles carry two
  local domain principles (§2 two-layer split, §3 coalescing-is-lossy),
  shifting canonical §3+ by one. Canonical §15 lands as **§16**; the
  §10 amendment attaches to this repo's **§11**; every transplanted
  §-reference is remapped and marked "this repo's numbering".
- **Term disambiguation:** documentation-ledger coalescing ([DOM-14])
  vs Engram's product memory coalescing — the state file and skill
  carry explicit disambiguation notes.
- Copied skills cite this plan and the source SHA, never foreign paths.
- Verification: `python3 bin/check-dom15-fixtures` exit 0; heading
  placement greps; docs-only change verified by inspection per [DOM-10].

## 3. Deviation Log

| Spec ref | Planned behavior | Actual behavior | Rationale | Spec proposal |
|----------|------------------|-----------------|-----------|---------------|

## 4. Review Findings and Dispositions

Round 1 (grok, scoped, 2026-07-14): BLOCKED on one P1 — the fixture
checker's docstring cited canonical "principle 12" where this repo's
numbering is §13 (fixed: dual-numbered). P2s: two missing
"this repo's numbering" annotations (added); one non-root-resolvable
path in the coalescing skill (fixed); residual term-collision awareness
noted as optional (A4 — no action, the two required surfaces carry the
disambiguation). Placement, remap, and the combined fold+wave landing
were judged sound. Round 2 waived: the P1 fix is a one-line docstring
edit verified by inspection — a re-review round would be performative
under the amended [DOM-11] lens; this note is the disclosed limitation.
