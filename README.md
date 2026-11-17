# Dojo

A Codex skill that runs a tournament of 4–16 competing solutions while preserving
useful ideas from eliminated answers. Based on Jake Schincariol's
[MIT-licensed Arena](https://github.com/Jakeschincariol/arena-skill).

## What it does

Each competitor receives the same task and a different strategy card. Competitors
attack and defend their answers; a separate judge selects the winners.

Dojo adds an idea pool:

1. Evaluate losing solutions and material removed during revisions.
2. Save useful contributions with exact sources, applicability, dependencies,
   evidence, and limitations.
3. In later rounds, retrieve potentially suitable contributions from a fixed pool
   snapshot. An idea can remain unused.
4. Freeze the ordinary answer (A0) before creating an optional candidate (A1).
5. Review A1 against A0. Accept only a supported improvement; otherwise retain A0.
6. Record justified retirements and recheck live solutions affected by disproof.

The pool belongs to one run. It is not cross-run memory, and there is no forced
merge or additional improvement round after the final.

## Requirements

- Python 3.8 or newer on macOS or Linux; standard library only.
- A Codex environment exposing the collaboration tools described in
  [SKILL.md](SKILL.md), with enough eligible worker contexts.
- Permission to write run artifacts and launch workers for the requested task.

The Python helper manages state and validates results. It does not call a model
API by itself. Codex orchestrates workers using the skill instructions. Host
concurrency limits can require serial work and context reuse.

## Install and use

Download this repository, then copy its contents into a new skill directory such
as `~/.codex/skills/dojo/`. Keep `SKILL.md`, all three Python modules, `prompts.md`,
`rubric.md`, and `strategies.json` together. Preserve the license and attribution.
Do not overwrite an existing installation without reviewing your local changes.

Ask Codex to use the installed Dojo skill with a task and competitor count:

> Use Dojo with 4 competitors to design a notes synchronization protocol. Preserve
> useful ideas from losing solutions, but incorporate them only when they fit.

The supported count is any integer from 4 to 16. `--quick` selects 16.
For the full orchestration contract, see [SKILL.md](SKILL.md).

## Inspect the helper

From this directory:

```bash
python3 bracket.py --help
python3 bracket.py plan --agents 4 --json
```

These commands do not launch agents. For a requested run, Codex writes a standalone
task file, initializes state, and follows the helper's next-step instructions:

```bash
python3 bracket.py init --agents 4 --task-file task.md --seed 7
python3 bracket.py next --json
python3 bracket.py status --json
```

Runs are stored under `.dojo/` by default. Use `--dir RUN_DIRECTORY` to select a
specific run. Workers write only assigned outputs and scratch files; the
coordinator collects results and commits shared state. Winning code is returned
for review rather than automatically applied to your project.

## Cost and limitations

A four-competitor run plans 22–26 logical jobs; a sixteen-competitor run plans
106–134. Retries, rechecks, optional baseline comparison, context startup, and tool
calls are additional. Job counts are not token estimates. The size of the task,
answers, and reused context affects cost and latency.

Judges and evaluators are models. They can miss flaws, useful ideas, or good fits.
Retrieval uses a bounded lexical shortlist, not guaranteed semantic recall.
Context reuse must be disclosed and can introduce bias. A validated run means
its collected judgments and protocol checks passed, not that its answer is proven
correct.

## Verification

```bash
python3 -B -m unittest discover -s tests
```

The 66-test suite covers counts 4–16, byes, adoption and rejection, preservation,
retirement conflicts, recovery, strict result validation, and CLI integration.

One four-competitor live design trial preserved five contributions, accepted one
addition after A0/A1 review, and retained another answer on a no-fit decision.
It reused one author/evaluator context and a separate judge/reviewer context.
These observations demonstrate workflow execution, not general quality gains.
Private trial outputs and development notes are excluded from this repository.

## Files

- `SKILL.md`: Codex orchestration instructions.
- `bracket.py`: tournament and CLI entry point.
- `dojo_protocol.py`: artifact and assignment protocol.
- `dojo_runtime.py`: idea pool, review, recovery, and runtime transitions.
- `prompts.md`: worker role contracts.
- `rubric.md` and `strategies.json`: scoring and strategy cards derived from Arena.
- `tests/`: deterministic protocol regression tests.

## License and credit

MIT. See [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md).
Dojo is a modified derivative of Arena, not an official Arena release or an
endorsement by its author. Original Arena copyrights are retained.
