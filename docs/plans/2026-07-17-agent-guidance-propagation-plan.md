# Agent-Guidance Propagation Plan (2026-07-17 delta wave)

Status: Active
Class: 5+P — normative spec text lands in the spec tree (the [DOM-14]
trigger bullet); [DOM-6]-material to future process. Hardening: N/A — no
[DOM-5] risky trigger (docs and guidance only).
Source: agent-guidance @ `b248e1c`. Prior pin: the 2026-07-14 wave
(engram `f92fa82`, source hub `2f7eff6`). This wave is the delta
`2f7eff6..b248e1c` restricted to the surfaces Engram carries. Source
content carried its own review rounds in agent-guidance; this repo's
review is scoped to the adaptation.

## 1. Goal and Scope

Adopt the delta between the 2026-07-14 pin (`2f7eff6`) and `b248e1c`:
the [DOM-14] fold-unit trigger bullet, the new
`designing-agent-facing-interfaces.md` runbook and its `interface-review`
skill, six coalescing-method refinements, two writing-plans lifecycle
bullets, the review-loops two-question prompt / scoped-change template /
verdict vocabulary, and the call-agent brief-artifact standard. Out of
scope: agent-guidance-local files (its own plans, lessons ledger,
repository map, bootstrap script, fixture checker) and the hub-native
`propagate-guidance` skill, which is not propagated by design.

Three wave items — the `brainstorming-to-plan` [DOM-15] triviality
wording, the `debugging` decision-hierarchy path form, and the
`external-skill-suites` plans/solutions-directory rewording — were found
already present in Engram's copies and needed no action.

## 2. Payload Checklist

| # | Item | Source | Target | Landed |
|---|------|--------|--------|--------|
| 1a | [DOM-14] fold-unit trigger bullet | hub `30c8b04` | `docs/specs/01-*.md` §14 | yes |
| 1b | Fold-unit + progress-model declaration | this plan | `docs/coalescing.md` | yes |
| 2 | New runbook (provenance/anchor adapted) | `b248e1c` | `runbooks/designing-agent-facing-interfaces.md` | yes |
| 2r | Runbook registration | wave | `agent-context/README.md`, `context.index.yaml` | yes |
| 3 | New skill (provenance/anchor localized) | `b248e1c` | `skills/interface-review/SKILL.md` | yes |
| 3r | Skill registration | this plan | `implementation/02-repository-map.md` §Skills | yes |
| 4 | Six coalescing refinements | hub `cc7ab30` | `skills/coalescing/SKILL.md` | yes |
| 5a | Planning Standard evidence bullet | `b248e1c` | `runbooks/writing-plans.md` | yes |
| 5b | Plan Lifecycle reviewed-text bullet | hub `fafd874` | `runbooks/writing-plans.md` | yes |
| 6 | Review-loops §4 prompt + trace, §4a, §6 vocab | `b248e1c` | `runbooks/review-loops-and-agent-bootstrap.md` | yes |
| 7 | Call-agent brief-artifact standard | `b248e1c` | `skills/call-agent/SKILL.md` | yes |

## 3. Invariants and Adaptations

| Divergence | Adaptation |
|------------|------------|
| engineering-principles run +1 (two local domain principles at §2, §3); hub §12 Enumerable = Engram §13 | Enumerable-contracts references in the new runbook and skill remapped to §13, marked "this repo's numbering". |
| Engram has **no** Canonicalize-at-Boundaries numbered principle (hub §2; Engram replaced it with local §2/§3) | Runbook principle 7's parenthetical rewritten to name the doctrine as a guidance-hub principle Engram carries in prose, not a numbered principle — no dangling §-number. |
| Copied skills/runbooks must cite Engram's provenance, not foreign plan paths | Runbook and skill Status/provenance blocks cite this plan + `b248e1c`; the hub lineage plan and hub promotion plan are quoted by name as foreign, non-resident. |
| The `interface-review` skill was promoted in the hub, not Engram | Status block states adoption-by-propagation; the hub promotion (3-citation threshold, hub coalescing run log) is recorded as foreign context, not an Engram promotion claim. |
| Term collision: documentation-ledger coalescing ([DOM-14]) vs Engram's product memory coalescing (moments/episodes/arcs) | Preserved intact — the coalescing skill and `docs/coalescing.md` keep their disambiguation notes; the new fold-unit declaration stays inside the documentation-ledger frame. |
| Plan Lifecycle bullet's `see docs/coalescing.md` pointer (hub tracks mm fold-up candidates there; Engram does not) | Repointed to agent-guidance's `docs/coalescing.md`, quoted as foreign lineage. |
| repository-map §Skills listed only README + _template; five skills already existed unlisted | Registered `interface-review` and backfilled the four prior skills so the navigational map is accurate; a bundled accuracy fix, noted here. |
| Review-loops section numbering matches the hub (§1–§6, not shifted) | Verified by heading grep before editing; §4 replaced in place, §4a inserted before §5, §6 vocabulary appended. |

## 4. Deviation Log

| Spec ref | Planned behavior | Actual behavior | Rationale | Spec proposal |
|----------|------------------|-----------------|-----------|---------------|

## 5. Review Findings and Dispositions

Scoped adaptation review (grok, read-only, 2026-07-17; §4a-form brief).
Verdict: **no blocker, zero findings; no fix work recommended before
land.** Verified: hub `b248e1c` end-state fidelity with no
intermediate-commit residue (PASS/BLOCKED, no retirement line); the §14
bullet splice structure-preserving; every principle-number remap
correct (Enumerable Contracts = this repo's §13; no leftover §12 or
dangling §2); the Canonicalize rewording makes no false local claim;
the documentation-vs-product-memory coalescing disambiguation intact
everywhere touched; provenance forms correct.

Accepted observations (no change): prior-wave pins on the coalescing
skill and state file remain at `2f7eff6` (multi-wave provenance
incomplete, not wrong — this plan and the run-log line carry the
`b248e1c` record); the hub-only `propagate-guidance` skill name appears
in interface-review prose as hub-canonical, not a local path claim;
cosmetic line-wrap at two remap sites.
