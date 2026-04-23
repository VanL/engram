# Codex Corpus Practical Evaluation Protocol

## Purpose

Mechanical validation proves that Engram can ingest real Codex-derived moments
and produce indexed summaries. Practical validation asks a different question:
would the context have helped a fresh-start agent answer later turns?

This protocol is deliberately manual for the first pass. It prevents scoring by
vibes while avoiding premature LLM judges or benchmark machinery.

## Checkpoint Definition

A checkpoint is one candidate future turn from a Codex session. Record:

- source file
- source pair index
- current user message to answer
- prior pairs available to memory
- next one to three source pairs used as oracle evidence only
- why the checkpoint is relatively timeless

Prefer checkpoints about architecture, planning, workflow, design, or conceptual
decisions. Avoid first-pass checkpoints that depend on exact live workspace
state, changing package versions, current command output, or hidden files.

## Baseline Answer

The baseline answer gets only the current user message. It does not get Engram
context, future turns, direct search, or hidden workspace state beyond what a
normal fresh-start agent would have.

This answer represents the no-memory control.

## Treatment Answer: Phase A

Phase A gets the same current user message plus rendered `build_context()` from a
vault that contains only prior pairs.

Do not allow Engram search, direct lookup, or future turns in Phase A. This tests
whether passive multi-horizon context assembly is useful by itself.

## Treatment Answer: Phase B

Phase B is deferred until Phase A produces useful signal.

It uses the same current user message and prior-only context, but allows a small
fixed number of Engram retrieval calls. The retrieval budget must be declared in
advance. Do not let the evaluator keep searching until it finds a good answer.

## Oracle Evidence

The next one to three source pairs are oracle evidence, not model input. They can
show whether the original conversation repeated context, corrected an answer, or
clarified something memory should have supplied.

The oracle is not perfect truth. It is evidence about what actually happened in
the conversation.

## Scoring

Score each checkpoint as one of:

- `helpful`: Engram context likely improves correctness, continuity, or reduces
  user restatement.
- `neutral`: Engram context causes no material difference.
- `harmful`: Engram context is stale, irrelevant, distracting, or misleading.

Also record a short rationale and cite the specific context item or missing
context item that drove the score.

## Gates

Do not start practical evaluation until the mechanical gate passes for the run.

Do not include future turns in the replay prefix for the treatment. If the
treatment sees oracle turns, the checkpoint is invalid.

Do not treat a useful-looking context snapshot as a pass unless it changes the
answer in a way the oracle evidence supports.

## First Manual Run Shape

1. Run mechanical validation with a small corpus sample.
2. Choose 5 to 10 relatively timeless checkpoints from the manifest.
3. Export checkpoint artifacts:

   ```bash
   ./.venv/bin/python -m engram.dogfood.codex_replay checkpoints \
       --manifest .engram-runs/codex-smoke/manifest.jsonl \
       --output .engram-runs/codex-smoke/checkpoints \
       --indices 50,100 \
       --oracle-pairs 3 \
       --tokens 2048
   ```

4. Write the baseline answer from `baseline.md`.
5. Write the Phase A treatment answer from `treatment-phase-a.md`.
6. Read `oracle.md` only after both answers are written.
7. Score the checkpoint in `scorecard.md`.
8. Summarize helpful, neutral, and harmful counts plus representative examples.

If most cases are neutral, that is not failure by itself. It may mean checkpoint
selection is weak, the corpus slice is too small, or passive context needs search
augmentation. The next action should follow the evidence rather than tune the
harness to make the result look better.
