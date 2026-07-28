# Agent-Guidance Propagation Plan (2026-07-28 delta wave)

Status: Active
Class: 3+P — no spec text lands this wave (guidance surfaces, one
skill, one runbook bullet, one entry-point bullet, two new executable
gates); [DOM-6]-material to future process, so the +P modifier applies.
Hardening: N/A — no [DOM-5] risky trigger (docs, guidance, and
read-only tooling only).
Source: agent-guidance @ `cec5666`. Prior pin: the 2026-07-17 wave
(Engram `b1d799e`, source hub `b248e1c`). This wave is the delta
`b248e1c..cec5666` restricted to the surfaces Engram carries (see §3,
Extraction provenance — the pin moved during extraction). Source content
carried its own review rounds in agent-guidance; this repo's review is
scoped to the adaptation.

## 1. Goal and Scope

Adopt the delta between the 2026-07-17 pin (`b248e1c`) and `cec5666`:
the coalescing skill's cue-portability paragraph, its repair-in-sweep
doctrine, its structured-status-index derivation clause and matching
Purpose-line update; the writing-plans closed-status-vocabulary bullet;
the `AGENTS.md` harness-scoping sentence; and two new executable gates
(`bin/check-doc-paths`, `bin/coalesce-check`) adapted to Engram's
layout and ledger format.

Out of scope (hub-local, deliberately not propagated): agent-guidance's
own plans, lessons ledger, coalescing state file, repository map, the
`bin/bootstrap-agent-guidance` scaffold and its plan-citation
adaptation, the hub-native `propagate-guidance` skill, and the hub's
CC0 relicensing (an owner decision about the hub's own artifact, not a
guidance rule).

## 2. Payload Checklist

| # | Item | Source | Target | Landed |
|---|------|--------|--------|--------|
| 1a | Cue-portability paragraph | hub `cec5666` | `skills/coalescing/SKILL.md` §2 | yes |
| 1b | Repair-in-sweep block (fold-up) | hub `cec5666` | `skills/coalescing/SKILL.md` §1 | yes |
| 1c | Structured-index derivation clause (fold-up) | hub `cec5666` | `skills/coalescing/SKILL.md` §1 | yes |
| 1d | Purpose-line update (fold-up) | hub `cec5666` | `skills/coalescing/SKILL.md` Purpose | yes |
| 2 | Closed status-vocabulary bullet (fold-up) | hub `cec5666` (re-synced) | `runbooks/writing-plans.md` Plan Lifecycle | yes |
| 3 | Harness-scoping sentence | hub `cec5666` | `AGENTS.md` | yes |
| 4a | New gate `bin/check-doc-paths` (adapted) | hub `cec5666` | `bin/check-doc-paths` | yes |
| 4b | New gate `bin/coalesce-check` (adapted) | hub `cec5666` | `bin/coalesce-check` | yes |
| 4r | Gate registration | this plan | `implementation/02-repository-map.md` Root Entry Points | yes |
| 5 | Plans index row | this plan | `docs/plans/README.md` Status Index | yes |
| 6 | Run-log line | this plan | `docs/coalescing.md` | yes |

## 3. Invariants and Adaptations

**Extraction provenance.** Extraction opened at hub `HEAD` =
`51626db`, where payload items 1b, 1c, 1d, and 2 existed only in the
hub's working tree. They were transplanted from that worktree and the
uncommitted origin was recorded. Mid-landing the hub committed them
(`e42762c`, then `cec5666`), and a fidelity re-diff against the
committed end-state found item 2 (the status-vocabulary bullet) had
been **revised before commit** — `retired` removed from the index-row
vocabulary, and `status-review` additionally declared "never a
retirement candidate". Item 2 was re-synced to the committed text;
items 1b, 1c, 1d were byte-identical and needed no change. Every
payload item is therefore retrievable at hub `cec5666`. This is the
end-state rule doing its job: the intermediate worktree state was
already stale by the time the wave landed.

| Divergence | Adaptation |
|------------|------------|
| engineering-principles run +1 (two local domain principles at §2, §3); hub §12 Enumerable Contracts = Engram §13 | `bin/check-doc-paths` docstring cites "engineering principle §13 (this repository's numbering; §12 canonically)", matching the existing convention in `bin/check-dom15-fixtures`. |
| Copied skills/tools must cite Engram's provenance, not foreign plan paths | Every adopted block's provenance parenthetical cites this plan + hub `cec5666`; the hub's own fold-up plan and taut's originating commit are quoted by name as foreign, non-resident lineage. |
| Term collision: documentation-ledger coalescing ([DOM-14]) vs Engram's product memory coalescing (moments → episodes → arcs) | Preserved and reinforced. The coalescing skill's Status-block disambiguation and `docs/coalescing.md`'s disambiguation block are untouched; the new repair-in-sweep block, which says "product behavior … stays out of scope", carries an added parenthetical naming Engram's product coalescing explicitly so "coalescing surfaces" cannot be misread as product surfaces. |
| Hub `AGENTS.md` puts the two overrides in a dedicated "Agent Permissions and Attribution" section; Engram carries them as the first three bullets of `## Shared Agent Context` | Sentence inserted as a bullet immediately after the self-attribution bullet and before `- Canonical shared context lives in …`. "The two overrides above" still resolves correctly (subagent authorization; self-attribution) — the intervening bullet is the scope note on the first override, not a third override. |
| Hub `check-doc-paths` has a `--scaffold` mode that bootstraps `bin/bootstrap-agent-guidance`; Engram has no scaffold script | `--scaffold` removed rather than left as a dead flag. Only `--root` tree mode ships. |
| SCAN surfaces are per-layout | Engram scans `docs/agent-context`, `docs/specs`, `skills` (dirs) and `AGENTS.md`, `docs/README.md`, `docs/coalescing.md` (files) — the same normative surfaces the hub scans, all of which exist here. `docs/implementation` and `docs/evaluation` are excluded for hub parity and recorded below as a deliberate, revisitable narrowing. `docs/lessons.md` and `docs/plans/` stay excluded for the hub's stated reasons (foreign/historical citations; post-closure path decay). |
| Claim regex scope | Kept at hub parity (`docs`, `skills`, `bin` prefixes). Engram additionally has `engram/` and `tests/` source trees whose paths are cited in guidance prose; widening the regex to cover them is a **separate, larger** change (it turns a doc gate into a code-path gate) and is recorded as a follow-up, not bundled here. |
| `coalesce-check` lessons derivation: hub's ledger is bare dated bullets (`^- YYYY-MM-DD`); Engram's is dated bullets **with a trailing colon** inside themed `###` sections, and `skills/coalescing/SKILL.md` §1 declares `grep -E '^- 20[0-9]{2}-[0-9]{2}-[0-9]{2}:' docs/lessons.md` | Regex adapted to `^- 20\d\d-\d\d-\d\d:` so the tool reproduces Engram's **declared** derivation exactly. Verified against `docs/coalescing.md`'s Deferral State, which records 2 entries past the (absent) watermark; the tool reports 2. |
| `coalesce-check` sibling list is hub-relative and includes `engram`; Engram is the local repo and `agent-guidance` is the sibling whose SHAs its run log cites | Sibling list retargeted to `agent-guidance`, `mm`, `weft`, `taut`, `backstitch`, `simplebroker` (self dropped, hub added). Without `agent-guidance` the existing run-log pins `2f7eff6` and `b248e1c` would report BROKEN. Convergent evidence: the hub independently made the same `agent-guidance` addition in `cec5666` while this wave was landing. |
| `bin/check-dom15-fixtures` was never listed in the repository map | Backfilled alongside the two new gate rows so the Root Entry Points table lists all three executable gates. A bundled navigational accuracy fix, disclosed here (same class as the 2026-07-17 wave's skills backfill). |
| `coalesce-check` state-file path | `docs/coalescing.md` — same path in both repos; no adaptation needed. |
| Engram's coalescing skill already carries the maintenance note "When an executable `coalesce-check` script exists, replace step 1's manual derivation with it and keep the commands here as the fallback." | That note becomes live on this landing with no edit required; it is the skill's own forward reference and was written for exactly this case. No text change made. |
| Engram's `origin/main` is behind local `HEAD` | `coalesce-check`'s publication check reports local-only pins informationally (exit 0). Expected, not a defect; see §5 for the observed output. Publication discipline is the owner's call. |

## 3a. Gate Baseline (recorded, not repaired)

`bin/check-doc-paths` is new here, so its first run is a baseline, not
a regression. It exits 1 on **6 pre-existing dangling path claims**,
all predating this wave and all outside its payload — per the
propagation standard, a receiving repo's own defects are theirs to
disposition, never "fixed" inside a propagation:

| Site | Claim | Class |
|------|-------|-------|
| `docs/specs/01-development-documentation-operating-model.md` §Related Plans (4 rows) | `docs/plans/2026-04-07-{development-documentation-foundation,plan-hardening-guidance,review-skills-bootstrap,specs-index-renumbering}-plan.md` | Hub plans inherited by the 2026-07-14 bootstrap and never resident here. Either retarget as foreign-by-name or drop the rows. |
| `docs/agent-context/runbooks/designing-agent-facing-interfaces.md:11` | `docs/plans/2026-07-14-agent-facing-interfaces-runbook-plan.md` | Foreign hub plan, correctly disclosed in prose as "not resident here" — but written as a backticked repo-relative path, which the gate cannot distinguish from a local claim. |
| `skills/interface-review/SKILL.md:10` | `docs/plans/2026-07-15-interface-review-skill-promotion-plan.md` | Same class. |

The second class is a **general finding owed upstream**: the
propagation standard tells consumers to cite hub plans by name, and
the natural rendering of "by name" is a backticked path — which this
gate then reads as a local claim. The fix is a citation form the gate
can tell apart (e.g. `agent-guidance: 2026-07-15-...-plan.md`, no
leading `docs/`), and it belongs in agent-guidance, not in a
one-repo patch.

`bin/coalesce-check` and `bin/check-dom15-fixtures` both exit 0 (see
the 2026-07-28 run-log line in `docs/coalescing.md` for the numbers).

## 4. Deviation Log

| Spec ref | Planned behavior | Actual behavior | Rationale | Spec proposal |
|----------|------------------|-----------------|-----------|---------------|

## 5. Review Findings and Dispositions

Scoped review (grok, read-only, 2026-07-28, §4a-form): **no blocker**.
Verified: e42762c fidelity (the worker's own end-state re-diff caught
and corrected the item-2 revision mid-flight — the transplant rule
working); term disambiguation intact at every touch, with the
repair-in-sweep block explicitly excluding Engram's product memory
coalescing; tool adaptations match the declared derivation (2 entries,
cross-checking the deferral record); SIBLINGS convergence with hub
cec5666. The six pre-existing danglers stay recorded owner items, and
the class-2 citation-form finding (foreign plans rendered as backticked
paths in two adopted surfaces) is owed upstream as a hub back-port.

| # | Finding | Disposition |
|---|---------|-------------|
