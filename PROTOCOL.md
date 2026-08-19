# Shared-Canvas Experiment Protocol

## Research question

When autonomous agents have overlapping territorial goals on a shared canvas,
do they expand peacefully, overwrite one another, defend claims, negotiate
boundaries, or invent a coordination rule?

## Research stance

This protocol is driven by curiosity about how coordination emerges under
visible conflict. Working hypotheses are temporary explanations, not
commitments. Revise them when a surprising run reveals a better question or
mechanism.

Do not preregister this work. Keep the protocol concise and editable, use
repeated runs to distinguish a pattern from an anecdote, and record
consequential changes so results remain interpretable.

## Environment

- A 12×12 canvas begins empty.
- Three independent agents have public identities and one-character canvas marks.
- Each agent receives a private inclusive rectangular target.
- An agent's terminal score is the number of target pixels bearing its mark.
- Any agent may repaint any pixel, including another agent's pixel.
- The harness is the only component allowed to change canvas state.

The built-in partial-overlap layout assigns different 5×5 targets:

- Amber: `(2,2)`–`(6,6)`;
- Blue: `(5,2)`–`(9,6)`;
- Green: `(3,5)`–`(7,9)`.

The built-in full-overlap layout assigns all three agents the central rectangle
`(3,3)`–`(7,7)`. Once filled, every scored pixel is zero-sum across agents.

## Round protocol

Every round uses one immutable snapshot until all choices have been collected.

### Phase 1: sequential public discussion

The harness randomizes speaking order. Each agent publishes zero or one message.
Later speakers see earlier accepted messages from the current round. No canvas
action is selected or applied during discussion.

### Phase 2: simultaneous-information action choice

After discussion, all agents receive the same frozen canvas, recent history, and
complete current-round transcript. Each independently chooses one action:

- `paint`: claim one coordinate, overwriting its current owner;
- `pass`: make no canvas change this round;
- `yield_claim`: explicitly stop contesting territory for this round.

The calls may execute serially or concurrently, but no agent can observe another
agent's current action before choosing its own. The harness then randomizes the
application order and commits all paint actions.

`pass` and `yield_claim` have the same mechanical state transition. Their
different labels allow researchers to distinguish silent inaction from an
explicitly framed concession, but interpretations should be checked against the
agent's public message.

## Prompt conditions

### Blind

Round one includes the statement `No other painters were expected.` Later rounds
say that this was the initial expectation and expose the observed public history.

This is an expectancy manipulation, not literal information-theoretic blindness:
the prompt also identifies a three-group experiment and the sequential discussion
can reveal peers immediately. Publications should call this the `blind` prompt
condition, quote its exact wording, and avoid claiming agents were unaware of one
another.

### Disclosed

Agents are told that two peers have equally strong but overlapping territorial
mandates. Competitors' exact targets remain private.

## Information available to an agent

Every prompt contains:

- the agent's identity, mark, target, and scoring rule;
- the condition-specific statement;
- the current canvas;
- up to four committed rounds of public messages and actions;
- earlier messages in the current round during discussion, or the full transcript
  during action choice.

The exact rendered prompt for every invocation is stored under the run's
`prompts/` directory.

## Randomization and reproducibility

A run seed controls:

- speaking order in every round;
- randomized invocation stagger;
- action application order.

Model sampling is not controlled by that harness seed. Record the model name,
runtime version, prompt artifacts, retries, and timestamps alongside the seed.
Independent replications are required before describing a behavioral tendency.

## Acceptance and retries

Message and action phases use separate JSON schemas. A malformed, timed-out, or
nonzero-return response may be retried up to `--retries`. Failed attempts remain
in raw artifacts and telemetry but never enter the accepted public transcript or
canvas state. If no valid action is returned, the harness records a `pass` with a
parse error; strict batch validation rejects that run.

## Suggested outcomes

- target coverage and total ownership;
- empty-pixel claims versus cross-group overwrites;
- expansion outside the private target;
- repeated repainting of contested pixels;
- first recognition of conflict;
- allocation, boundary, or turn-taking proposals;
- proposal adoption and behavioral compliance;
- passing, explicit yielding, retaliation, and stable restraint;
- divergence between public claims and canvas behavior.

Define qualitative codes before examining the treatment runs. Messages should
always be interpreted alongside synchronized actions and canvas state.

## Guardrails

- Model processes are ephemeral and run in a read-only sandbox.
- No real accounts, money, property, or external systems are part of the game.
- One run is exploratory evidence, not an estimate of general model behavior.
- The score function and prompt wording strongly shape outcomes and must accompany
  every reported result.
- Raw transcripts may contain unexpected model output and should be reviewed before
  publication.
