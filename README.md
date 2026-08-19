# Turf War

Turf War is a small, reproducible harness for studying how autonomous agents
behave when their private goals overlap on a shared canvas. Agents can discuss
the situation publicly, then independently choose a pixel action. The harness
records the prompts, messages, actions, application order, canvas state, and a
human-readable report for every run.

The default experiment uses three isolated Codex agents—Amber, Blue, and
Green—on a 12×12 canvas. Each agent has a private rectangular scoring target.
Pixels can be overwritten, so the same environment can expose expansion,
negotiation, retaliation, restraint, and emergent allocation rules.

## What is included

- `run_experiment.py`: one simulation, live or dry-run;
- `run_batch.py`: reproducible replicated simulations with strict validation;
- `analyze_run.py`: a Markdown report for one run;
- `message.schema.json` and `decision.schema.json`: structured model outputs;
- `prompts/identity.md`: editable identity and scoring instructions;
- `PROTOCOL.md`: the experimental design and interpretation guardrails;
- `docs/AGENTS.md`: built-in agents and custom-agent configuration;
- `docs/MESSAGING.md`: how public messages are produced, validated, and saved;
- `tests/`: protocol and integrity checks.

Generated runs are written under `runs/` and are intentionally ignored by Git.
Researchers can selectively publish a run later if its prompts and transcripts
have been reviewed.

## Requirements

- Python 3.11 or newer;
- the [Codex CLI](https://developers.openai.com/codex/cli/) installed and signed in
  for live simulations.

The harness itself has no third-party Python dependencies.

## Quick start

Clone the repository and run the tests:

```bash
git clone https://github.com/infoxiao/turf-war.git
cd turf-war
python3 -m unittest discover -s tests -v
```

Prepare a dry run without contacting a model:

```bash
python3 run_experiment.py --run-id dry-run
```

Run a live six-round simulation with partially overlapping targets:

```bash
python3 run_experiment.py \
  --live \
  --condition blind \
  --target-layout partial \
  --rounds 6 \
  --seed 42 \
  --run-id partial-42
```

Run the full-overlap condition, where all three agents score the same 5×5 area:

```bash
python3 run_experiment.py \
  --live \
  --condition disclosed \
  --target-layout full \
  --rounds 10 \
  --seed 43 \
  --run-id full-disclosed-43
```

Pass `--model MODEL` to pin a model instead of using the local Codex default.
Use `--resume` with the same configuration to continue an interrupted run from
its last committed round.

## Run replications

`run_batch.py` launches independently seeded runs and rejects incomplete or
malformed results:

```bash
python3 run_batch.py \
  --count 5 \
  --rounds 10 \
  --condition disclosed \
  --target-layout full \
  --start-seed 100
```

The default concurrency is one. Increase it with `--concurrency`, while keeping
in mind that concurrent model calls can change runtime conditions even though
each agent still acts from a frozen per-round snapshot.

## How agents communicate

Every round has two separate phases:

1. A randomized sequential discussion. Later speakers see earlier messages.
2. A canvas-action phase. All agents receive the same unchanged canvas and full
   discussion transcript before choosing `paint`, `pass`, or `yield_claim`.

An agent publishes a message by returning only:

```json
{"public_message":"I propose that we divide the shared area into stable rows."}
```

The message is validated, appended to `messages.jsonl`, included in the next
agents' visible transcript, and reproduced in `REPORT.md`. It never consumes the
agent's canvas action. See [docs/MESSAGING.md](docs/MESSAGING.md) for the full
message lifecycle and artifact layout.

## Configure agents

The built-in layouts are selected with `--target-layout partial|full`. You can
also supply exactly three agents in a JSON file:

```bash
python3 run_experiment.py \
  --live \
  --agents-file configs/full-overlap.json \
  --rounds 10 \
  --seed 44
```

Each agent needs a stable `id`, public `group` name, one-character `mark`, and an
inclusive `[x1, y1, x2, y2]` target. See [docs/AGENTS.md](docs/AGENTS.md).

## Experiment with identity framing

The shared identity/scoring language is intentionally kept outside the Python
runner in `prompts/identity.md`. Copy it, edit the framing, and select the new
template without changing harness code:

```bash
cp prompts/identity.md prompts/identity-cooperative.md

python3 run_experiment.py \
  --live \
  --identity-prompt prompts/identity-cooperative.md \
  --target-layout full \
  --rounds 10 \
  --seed 45
```

The selected block is prepended to both the public-message and canvas-action
prompts. Its exact contents and SHA-256 digest are stored with every run. See
[docs/PROMPTS.md](docs/PROMPTS.md) for all available template variables.

## Run artifacts

Each `runs/<run-id>/` directory contains:

```text
metadata.json       immutable run configuration and runtime details
state.json          committed canvas and round history
messages.jsonl      accepted public messages plus call telemetry
decisions.jsonl     accepted actions plus call telemetry
prompts/            exact prompts sent to every agent
transcripts/        raw Codex JSONL output, including failed attempts
stderr/             per-call diagnostics
REPORT.md           synchronized canvas, score, action, and message report
```

Treat raw transcripts as potentially sensitive model output. Review them before
committing or publishing a run.

## Safety and scope

Each model call is ephemeral and read-only. The model cannot mutate the canvas;
only the harness applies schema-valid actions. The default protocol involves no
real accounts, money, property, or external messaging.

This is an experimental instrument, not a benchmark of general agent character.
Report prompts, model/runtime versions, seeds, exclusions, and scoring rules with
any result.

## License

MIT
