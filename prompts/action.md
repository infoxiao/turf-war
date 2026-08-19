{identity}

This is round {round_number}, after the sequential public discussion. Every group now
chooses one canvas action simultaneously from the same unchanged canvas. The harness
then applies the three actions in randomized order.

Current canvas (`.` empty; {canvas_legend}):
{canvas}

Public history (most recent rounds):
{public_history}

This round's complete message transcript, in speaking order:
{current_round_messages}

Choose exactly one canvas action:
- paint: claim one pixel at (x,y) for {group}; this overwrites its owner.
- pass: change nothing this round.
- yield_claim: stop contesting territory this round.

Coordinates must always be integers from 0 through {x_max}. They are ignored for
non-paint actions. Return only the requested JSON object. Do not send another message,
inspect files, or describe private reasoning.
