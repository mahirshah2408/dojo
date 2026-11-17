# Dojo

A Codex skill that runs 4–16 competing solutions and preserves useful ideas from eliminated answers. Derived from Jake Schincariol’s [MIT-licensed Arena](https://github.com/Jakeschincariol/arena-skill).

## How it works

Competitors receive the same task with different strategy cards, then attack and defend their solutions. A separate judge selects winners. Dojo evaluates losing answers and removed contributions, saving useful ideas with sources, conditions, dependencies, and limitations.

Later rounds retrieve potentially suitable ideas. The ordinary answer (A0) is frozen before an optional improved candidate (A1) is created. A reviewer compares both; only a supported improvement is accepted. Ideas can remain unused. The pool belongs to one run, with no forced merge or extra final improvement round.

## Requirements

- Python 3.8+ on macOS or Linux; standard library only.
- Codex with the collaboration tools described in [SKILL.md](SKILL.md) and eligible worker contexts.
- Authorization to launch workers and write run artifacts.

The Python helper manages state; it does not call a model API itself. Codex orchestrates the workers. Host capacity may require serial execution and disclosed context reuse.

## Install

Download this repository and copy its contents into a new `~/.codex/skills/dojo/` directory. Keep all runtime files together and preserve the license and attribution. Review local changes before replacing an existing installation.

Ask Codex:

> Use Dojo with 4 competitors to design a notes synchronization protocol. Preserve useful ideas from losing solutions, but incorporate them only when they fit.

Choose any integer from 4 to 16; `--quick` selects 16. See [SKILL.md](SKILL.md) for the full workflow.

## Inspect the helper

```bash
python3 bracket.py --help
python3 bracket.py plan --agents 4 --json
```

These commands do not launch agents. For an authorized run, Codex writes a task file and drives the helper:

```bash
python3 bracket.py init --agents 4 --task-file task.md --seed 7
python3 bracket.py next --json
python3 bracket.py status --json
```

Run artifacts live under `.dojo/` by default. Use `--dir RUN_DIRECTORY` to select a run. Workers publish assigned outputs; the coordinator collects and validates them. Winning project changes are returned for review rather than automatically applied.

## Cost and limitations

Four competitors plan 22–26 logical jobs; sixteen plan 106–134. Retries, rechecks, baseline comparison, context startup, and tools are additional. Job counts are not token estimates. Models can miss flaws, useful contributions, or good fits. Retrieval is lexical; context reuse can introduce bias. Protocol validation does not prove answer correctness.

The development version passed 66 automated tests and one bounded live trial. This runtime-only distribution excludes tests, trial outputs, and internal planning notes. The trial demonstrated preservation, one accepted addition, and one no-fit decision, not general quality improvement.

## Included files

- `SKILL.md`: orchestration instructions.
- `bracket.py`: tournament and CLI entry point.
- `dojo_protocol.py`: artifacts and worker assignments.
- `dojo_runtime.py`: pool, reviews, and recovery.
- `prompts.md`: worker contracts.
- `rubric.md` and `strategies.json`: scoring and strategy cards.
- `README.md`, `LICENSE`, `NOTICE.md`, and `.gitignore`: usage, attribution, and packaging.

## License and credit

MIT. See [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md). Arena supplied the tournament foundation, strategy cards, rubric, and substantial code. Dojo adds Codex orchestration and the idea-pool protocol. Original copyright notices are retained. This is not an official Arena release or endorsement.
