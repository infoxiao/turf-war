# Prompt templates

The identity and scoring block shared by both model phases lives in
`prompts/identity.md`. Keeping it separate makes identity framing an explicit,
versionable experimental variable rather than a Python-code change.

## Use a custom identity prompt

Copy the default, edit it, and pass the new file to a run:

```bash
cp prompts/identity.md prompts/identity-cooperative.md

python3 run_experiment.py \
  --live \
  --identity-prompt prompts/identity-cooperative.md \
  --target-layout full \
  --rounds 10 \
  --seed 45
```

The same option works with replications:

```bash
python3 run_batch.py \
  --identity-prompt prompts/identity-cooperative.md \
  --count 5 \
  --start-seed 100
```

## Available variables

Templates use Python-style `{variable}` placeholders:

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

Unknown variables fail before a run is created. To include literal braces, write
`{{` and `}}`.

A template may omit any variable. This makes it possible to test identity-only,
role-neutral, goal-neutral, competitive, or cooperative framings while leaving
the discussion and action mechanics unchanged.

## Reproducibility

Every new run records:

- the template filename in `metadata.json`;
- a SHA-256 digest in `metadata.json`;
- the complete source template at `prompts/identity-template.md`;
- every fully rendered message and action prompt under the round directories.

Resuming a run with different identity wording is rejected. Batch runs also
validate the digest before reusing an existing replication.
