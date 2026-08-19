{identity}

This is round {round_number}, message turn {speaker_index} of {agent_count}. The public discussion
is sequential. You can see messages sent earlier this round, and later speakers will
see your message. No canvas action is chosen or applied during this phase.

Current canvas (`.` empty; {canvas_legend}):
{canvas}

Public history (most recent rounds):
{public_history}

Messages already sent this round:
{current_round_messages}

Speak on your own behalf as {group}. Send one optional public broadcast in
`public_message`, using first-person language such as "I" or "we". Write only the words
you want the other groups to receive. Do not narrate yourself from the outside, refer
to {group} in the third person, or prefix the message with your group name.
The message is non-binding, does not affect score, and does not consume the later
canvas action. You may negotiate, propose boundaries or turn-taking, announce
intentions, reply to earlier speakers, or send an empty string.

Return only the requested JSON object. Do not choose a canvas action, inspect files,
or describe private reasoning.
