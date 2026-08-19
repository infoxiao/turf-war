# Public messaging

Public messages are a first-class experimental channel, separate from canvas
actions. The harness records exactly what each peer could observe and when.

## Round lifecycle

1. The harness freezes the current canvas and recent public history.
2. It randomizes the three-agent speaking order.
3. Speaker one sees no current-round messages.
4. Speaker two sees speaker one's accepted message.
5. Speaker three sees both earlier accepted messages.
6. All three agents then receive the frozen canvas and the complete transcript
   before independently selecting a canvas action.
7. The harness randomizes action application order and commits the round.

No action is visible during discussion, and no agent sees another agent's chosen
action before selecting its own.

## Publishing a message

The message-phase response must match `message.schema.json`:

```json
{"public_message":"I will claim the upper row and avoid repainting your pixels."}
```

An empty string is a valid choice. A nonempty message must be at most 240
characters, contain no raw control characters, and speak directly without
prefixing itself with the agent's group name. Invalid responses are retried up
to the configured limit and never enter the public transcript.

Once accepted, a message is published inside the simulation by being:

- made visible to later speakers in the same round;
- included in every agent's action prompt;
- appended to `messages.jsonl`;
- stored in the committed `state.json` round record;
- shown in subsequent public history and the generated `REPORT.md`.

Messages are non-binding, do not change score, and do not replace the later
canvas action.

## Artifact paths

For round 1, a run typically contains:

```text
prompts/round-01/messages/01-blue-identity-01.md
transcripts/round-01/messages/01-blue-identity-01-attempt-01.jsonl
stderr/round-01/messages/01-blue-identity-01-attempt-01.log
messages.jsonl
```

The randomized order means the filename's identity can differ across runs.
Rejected attempts remain in raw artifacts for auditability but are not exposed
to peers.

## Publishing run artifacts externally

`runs/` is ignored by default because raw model output should be reviewed first.
To publish an example run, inspect its prompts, transcripts, stderr, metadata,
and report; remove any environment-specific or sensitive content; then copy the
curated artifact into a deliberately tracked directory such as
`examples/runs/<run-id>/`.
