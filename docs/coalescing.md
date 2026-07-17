# Coalescing State (documentation ledger)

Status: Active — governed by [DOM-14] in
`docs/specs/01-development-documentation-operating-model.md` (adopted
from agent-guidance @ `2f7eff6` via
`docs/plans/2026-07-14-agent-guidance-propagation-plan.md`).

**Disambiguation:** this file governs coalescing of the *documentation
ledger* (lessons, plans) per [DOM-14]. It is unrelated to Engram's
product memory coalescing (moments → episodes → arcs), which is
governed by `docs/specs/10-minimum-memory-model.md` and
`docs/specs/13-context-assembly-and-arcs.md`.

Owner: any agent that observes a tripped threshold at session start.
Boundary: lessons, plans, and skill/runbook promotion. Specs and
implementation docs are living documents and are never coalesced.
Verification: the run log below plus inspection gates. Required action:
the session-start check is **read-only**; all writes happen only inside
an authorized maintenance task (`skills/coalescing/SKILL.md`).

## Thresholds

| Tier | Trigger (derived count) | Threshold | Age floor |
|------|------------------------|-----------|-----------|
| Lessons | dated ledger entries after the lessons watermark | 10 | 30 days, never entries cited by an active plan or in a still-accumulating theme |
| Plans | plans with status completed/superseded, not `exemplar`, and no retired-ledger line | 5 | none — the harvest gate and two-step retirement are the guards |
| Promotion | distinct citations of the same workflow theme since the promotion watermark | 3 | n/a |

## Fold Unit and Progress Model

Per [DOM-14], each repository declares its fold unit and the matching
progress model. Engram's documentation ledger is **repo-wide, not
domain-grouped**: lessons are one dated ledger and plans are one flat
index, so the fold unit is the whole tier, counted repo-wide over
fold-eligible (cold, unfolded) material only — entries within the age
floor or already folded do not count. The progress model is a single
**date-plus-SHA watermark per tier** (the Watermarks table below). A
date cursor is valid here because lessons fold oldest-first by age
floor, not by theme-cluster across dates; if a tier ever begins folding
by theme-cluster, it must switch to a fold-records index per the
[DOM-14] trigger bullet, because a date cursor would then falsely claim
older unfolded material behind it was folded.

## Watermarks

| Tier | Distilled through | Source SHA |
|------|-------------------|------------|
| Lessons | (none — first sweep below) | — |
| Plans | (none — first sweep pending) | — |
| Promotion | (none) | — |

## Deferral State

| Tier | Checked through (date, SHA) | Counts at check | Reason deferred | Reconsider when |
|------|------------------------------|-----------------|-----------------|-----------------|
| Lessons | 2026-07-14, `f92fa82` | 2 past (no) watermark — under threshold 10; both within age floor | Not tripped; nothing foldable | Count changes or entries age past 30 days |
| Plans | 2026-07-14, first sweep | not derived | Plan statuses not yet indexed; the 21 plans predate the status index | A sweep is authorized with plans in scope |
| Promotion | 2026-07-14, first sweep | not derived | Derive at a future sweep | — |

## Run Log

| Date | Tier(s) | Source SHA | Claim |
|------|---------|------------|-------|
| 2026-07-14 | all | `f92fa82` (checked-deferred; nothing folded) | Layer adopted from agent-guidance `2f7eff6`; first sweep ran in the same unit per the sweep-after-propagation rule. Lessons: 2 dated entries, under threshold, within age floor. No watermark advanced. |
