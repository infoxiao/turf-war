# Prompt templates

All stable agent-facing instructions live under `prompts/` rather than inside
the Python runner:

| Template | Controls |
| --- | --- |
| `identity.md` | Identity, private target, scoring rule, and condition context |
| `message.md` | Sequential discussion and public-message behavior |
| `action.md` | Canvas actions, overwriting, coordinate bounds, and response behavior |
| `conditions/*.md` | Blind/disclosed condition context selected by round |

At runtime the identity template is rendered first and supplied to each phase
template as `{identity}`. The runner only computes dynamic experiment state such
as the canvas, history, transcript, round number, and speaker position.

## Use custom prompts

Copy the defaults, edit them, and pass any combination to a run:

```bash
cp prompts/identity.md prompts/identity-cooperative.md
cp prompts/message.md prompts/message-terse.md
cp prompts/action.md prompts/action-custom.md
cp -R prompts/conditions prompts/conditions-custom

python3 run_experiment.py \
  --live \
  --identity-prompt prompts/identity-cooperative.md \
  --message-prompt prompts/message-terse.md \
  --action-prompt prompts/action-custom.md \
  --condition-prompts-dir prompts/conditions-custom \
  --target-layout full \
  --rounds 10 \
  --seed 45
```

The same options work with replications:

```bash
python3 run_batch.py \
  --identity-prompt prompts/identity-cooperative.md \
  --message-prompt prompts/message-terse.md \
  --action-prompt prompts/action-custom.md \
  --condition-prompts-dir prompts/conditions-custom \
  --count 5 \
  --start-seed 100
```

## Identity variables

`identity.md` supports:

| Variable | Meaning |
| --- | --- |
| `{group}` | Public group name, such as `Amber` |
| `{agent_id}` | Stable machine ID, such as `amber` |
| `{mark}` | One-character canvas mark |
| `{agent_count}` | Number of configured agents |
| `{width}`, `{height}` | Canvas dimensions |
| `{x1}`, `{y1}`, `{x2}`, `{y2}` | Inclusive target bounds |
| `{target_total}` | Number of pixels in the private target |
| `{condition_context}` | Round-specific blind or disclosed wording |

## Message variables

`message.md` supports:

| Variable | Meaning |
| --- | --- |
| `{identity}` | Fully rendered identity template |
| `{round_number}` | Current round |
| `{speaker_index}` | Current position in randomized speaking order |
| `{canvas}` | Current frozen canvas |
| `{canvas_legend}` | Mark-to-group mapping |
| `{public_history}` | Recent committed messages and actions |
| `{current_round_messages}` | Messages from earlier speakers this round |
| `{group}`, `{agent_id}`, `{mark}` | Current agent identity fields |
| `{agent_count}` | Number of configured agents |
| `{width}`, `{height}` | Canvas dimensions |

## Action variables

`action.md` supports:

| Variable | Meaning |
| --- | --- |
| `{identity}` | Fully rendered identity template |
| `{round_number}` | Current round |
| `{canvas}` | Unchanged canvas shared by all action calls |
| `{canvas_legend}` | Mark-to-group mapping |
| `{public_history}` | Recent committed messages and actions |
| `{current_round_messages}` | Complete current-round message transcript |
| `{group}`, `{agent_id}`, `{mark}` | Current agent identity fields |
| `{agent_count}` | Number of configured agents |
| `{width}`, `{height}` | Canvas dimensions |
| `{x_max}`, `{y_max}` | Largest valid coordinate on each axis |

Unknown variables fail before a run is created. Templates may omit variables.
To include literal braces, write `{{` and `}}`.

## Condition files

The condition directory must contain these plain Markdown files:

```text
blind-initial.md    blind condition in round one
blind-observed.md   blind condition after round one
disclosed.md        disclosed condition in every round
```

Condition files do not use template variables. Keeping them separate makes it
easy to change expectancy or disclosure framing without editing Python or the
rest of the identity prompt.

## Reproducibility

Every new run records each template's filename and SHA-256 digest in
`metadata.json`. Complete source copies are stored as:

```text
prompts/identity-template.md
prompts/message-template.md
prompts/action-template.md
prompts/conditions/blind-initial.md
prompts/conditions/blind-observed.md
prompts/conditions/disclosed.md
```

Every fully rendered prompt is also stored under its round and phase directory.
Resuming with any changed template is rejected. Batch runs validate all three
digests before reusing an existing replication.
