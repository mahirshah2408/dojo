---
name: dojo
description: >-
  Run a Codex solution tournament with 4–16 competitors, independent judgments,
  and a pool preserving useful contributions from eliminated solutions. Use when
  the user asks to run Dojo or make agents compete. Discussing or editing the
  skill does not authorize a tournament.
---

# Dojo

Use `python3 /absolute/path/to/this/skill/bracket.py` as `DOJO` below.
The coordinator schedules work and commits state; it never competes or chooses
winners. Worker contracts live in [prompts.md](prompts.md), frozen for each run.
Python 3.8+ and standard-library modules are required on macOS/Linux.

## Start a requested run

Use the user's task and constraints verbatim. If task or competitor count cannot
be inferred, ask for that missing information. Choose an explicit integer 4–16;
`--quick` selects 16. `--wave` defaults to 2 and is only an upper bound.

Write a standalone task file in the writable project directory, including its
acceptance criteria and relevant source paths. If the user rejected a previous
answer, save that answer as a baseline without rewriting it.

```bash
DOJO plan --agents 8 --json
DOJO init --agents 8 --task-file task.md --seed 7
```

Optional: `--baseline-file baseline.md`, `--wave 2`, `--dir RUN_DIRECTORY`.
Omit a seed to select and record one. Runs live under `.dojo/` by default.
Every subsequent run command accepts `--dir`; otherwise `.dojo/LATEST` is used.
Never change the requested competitor count merely to fit worker capacity.

## Drive the state machine

1. Run `DOJO next --json`. Follow its phase and listed job IDs.
2. For a worker phase, run `DOJO prompts PHASE` to prepare its jobs.
3. Bind each job with `DOJO assign JOB_ID --worker ACTUAL_CONTEXT_ID`. This
   writes and returns the final prompt path. A prepared but unassigned prompt
   path is not yet runnable. Never invent a worker identity to bypass history.
4. Dispatch the returned prompt to its assigned worker, then run `DOJO collect`
   after published outputs arrive. Collection validates identities, hashes,
   schemas, role decisions, and records retry or deferral states.
5. Repeat `next`. When it reports advance, use `DOJO advance --round N` with
   that exact round number. Repeating closure of that round is a no-op.
6. When it reports done, inspect `DOJO winner --json` before delivery.

For a new context use `collaboration.spawn_agent` with a unique task name and
`fork_turns: "none"`. Assign its actual canonical identity before it begins work;
if identity is not available beforehand, start it idle, assign, then follow up.
Use `collaboration.followup_task` for an eligible existing context. Its whole
brief is: `Read <absolute prompt path> and follow it exactly.`

Workers write only their assigned output and scratch files. Results are JSON
objects containing the exact `assignment` from the brief and a role-specific
`result`. Publish via a temporary file and atomic rename. Code solutions contain
patches or full files; workers do not edit the user's project directly.

## Roles and capacity

Count the coordinator and existing contexts against host capacity. Use only
exposed lifecycle tools; finishing or interrupting a worker does not necessarily
release its slot. Do not recursively delegate or repurpose unrelated agents.

Keep a judge context that has never competed, attacked, defended, or built a
candidate. The evaluator must differ from that match's judge. A candidate is a
continuation in its ordinary defender's context. Its reviewer cannot be its author
or an idea nominator. A match judge may review additions when eligible, but this
is disclosed reuse, not full independence. Recheck workers cannot be the affected
solution's author or the idea's nominator.

On a four-slot host, reuse two author contexts and one dedicated judge as needed.
An eligible author context can perform idea evaluation in a later phase; track
that nomination history. Prefer fresh review contexts when supported. The helper
tracks actual assignment history and prevents concurrent jobs in one context.
Read metadata in `dojo.json` and use `collaboration.list_agents` to recover context
identities on resume. Do not read competitor solutions to make coordinator judgments.

Wait in intervals of at most 60 seconds and provide progress updates. If no
eligible worker exists for an optional candidate, review, or evaluation, use
`DOJO defer JOB_ID`; keep A0 or unevaluated captures as appropriate. Never relax
role restrictions to fill a slot.

## Tournament and idea pool

Each round performs attacks, ordinary defenses, optional candidate continuations
and reviews, match judgments, then idea evaluations. Byes carry their accepted
version unchanged. The helper seals A0 before optional candidate work and records
source-backed diffs at revision boundaries, including removals from winners.

The evaluator considers the actual loser and both sides' captures. Preserve only
useful supported contributions with source passages, applicability, dependencies,
limitations, and evidence. An empty successful evaluation is valid. Pending ideas
need a concrete verification question; retired ideas retain their evidence/history.

Every competitor uses the same fixed round snapshot. Candidate workers retrieve
with `DOJO pool --job JOB_ID --query "concrete need" --limit 5`. This is a bounded
lexical shortlist, not a semantic guarantee. Inspect conditions and make a focused
follow-up query when warranted. Non-retrieval does not reject an idea. Storage has
no fixed idea quota, and an idea may remain unused for the entire run.

A defender may make one coherent optional candidate A1. An independent reviewer
compares complete A0/A1, prior accepted work, defense, and diff. Acceptance needs
verified benefit, preserved constraints, and no important regression. Baseline
soundness must agree with A0 usability. If A0 is unusable, acceptance additionally
requires explicit evidence verifying that A1 fixes its identified failures. Tie, uncertainty, rejection, or exhausted review retries retain usable
A0. No candidate repair loop. The normal judge sees exactly the accepted version.

Retire only with supported disproof, adequate duplication, or supersession that
preserves useful conditions and important tradeoffs. Conflicting proposals stay
available pending resolution. Disproof blocks further use and triggers scoped
rechecks of current dependent versions. Unresolved correctness alerts block
validated advancement/delivery. Do not undo patches or replay past matches.
Final-round ideas are preserved without an extra champion-improvement round.

## Failures and resumption

Use `DOJO fail JOB_ID --reason "specific failure"` for a missing assigned output.
Malformed outputs are handled by collection. Spawn/attack/defend get one retry,
then explicit failed placeholders. Match/final judges get two retries, then block.
Evaluation/review/recheck get one retry. Failed evaluation/review defer; failed
recheck blocks. Candidate construction gets one attempt and cannot start a repair
loop. Check the recorded outcome rather than resubmitting indefinitely.

An explicit `DOJO recover EVALUATION_JOB_ID` can retry deferred preservation using
its original inputs; it never changes past snapshots or match outcomes. This
recovery has its own bounded attempts and is not automatically repeated.

On interruption, stop scheduling, interrupt active Dojo workers, and report the
saved run directory. Resume through status and next, preserving assignment
history. Legacy version-1 runs are read-only; do not silently migrate their missing
capture/review history. Manual winner overrides are disabled in protocol 2.

## Deliver and disclose

Deliver the complete champion only when `winner` reports a usable validated
result. Explain why it won, baseline comparison if present, number of competitors,
run directory, incomplete preservation, unresolved limitations, and context reuse.
A bracket survivor with unusable output is not a successful answer. Apply winning
project changes only within the user's existing authorization.

Plan counts distinguish minimum jobs from optional continuations/reviews. A fresh
16-competitor run plans 106–134 jobs, plus one optional baseline comparison.
Retries, explicit recovery, exceptional rechecks, context startup, and tool calls
are additional. Recorded dispatches are not a token estimate or an exact count
of all host/model operations. Wave estimates assume available eligible contexts.

Protocol tests establish state-machine behavior. They do not establish that models
extract every useful idea, find every fit, or always improve answer quality.
