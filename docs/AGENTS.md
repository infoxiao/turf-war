# Agent setup

Turf War uses three independent model invocations with persistent public
identities. They share no hidden conversational state: continuity comes only
from the canvas and public history rendered into each new prompt.

## Built-in agents

| ID | Public identity | Canvas mark | Partial target | Full target |
| --- | --- | --- | --- | --- |
| `amber` | Amber | `A` | `(2,2)`–`(6,6)` | `(3,3)`–`(7,7)` |
| `blue` | Blue | `B` | `(5,2)`–`(9,6)` | `(3,3)`–`(7,7)` |
| `green` | Green | `G` | `(3,5)`–`(7,9)` | `(3,3)`–`(7,7)` |

Select a built-in configuration with `--target-layout partial` or
`--target-layout full`.

## Custom configuration

Pass `--agents-file PATH` to replace the built-in layout. The file must contain
a JSON array of exactly three objects:

```json
[
  {
    "id": "amber",
    "group": "Amber",
    "mark": "A",
    "target": [2, 2, 6, 6]
  }
]
```

Repeat that shape for all three agents. The harness validates that:

- IDs, group names, and one-character marks are unique;
- targets contain four integer coordinates;
- targets are ordered inclusive rectangles inside the 12×12 canvas.

The full resolved configuration is copied into `metadata.json`, so the original
configuration file is not required to reproduce or audit the prompt content.

## Runtime isolation

Each message and action is a fresh `codex exec` call with:

- an ephemeral session;
- a read-only sandbox;
- user configuration and repository rules ignored;
- a phase-specific JSON output schema.

This intentionally prevents hidden cross-agent memory or local file mutation.
To add another runtime, replace or generalize `call_codex()` while preserving
the prompt artifacts, structured outputs, retry telemetry, and frozen action
snapshot. Those properties are part of the experimental protocol.
