#!/usr/bin/env python3
"""Generate a report for a shared-canvas turf-war run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    return parser.parse_args()


def table(headers: Iterable[str], rows: Iterable[Iterable[Any]]) -> str:
    headers = list(headers)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(str(value).replace("|", "\\|").replace("\n", " ") for value in row)
            + " |"
        )
    return "\n".join(lines)


def canvas_block(state: Dict[str, Any], agents: List[Dict[str, Any]]) -> str:
    marks = {agent["id"]: agent["mark"] for agent in agents} | {None: "."}
    return "\n".join("".join(marks[owner] for owner in row) for row in state["pixels"])


def main() -> None:
    args = parse_args()
    run_dir = args.run_dir.resolve()
    metadata_path = run_dir / "metadata.json"
    state_path = run_dir / "state.json"
    if not metadata_path.is_file() or not state_path.is_file():
        raise SystemExit(f"Not a turf-war canvas run: {run_dir}")
    metadata: Dict[str, Any] = json.loads(metadata_path.read_text(encoding="utf-8"))
    state: Dict[str, Any] = json.loads(state_path.read_text(encoding="utf-8"))
    action_counts: Dict[str, int] = {}
    overwrites = 0
    empty_claims = 0
    round_sections: List[str] = []
    for record in state["rounds"]:
        for change in record["changes"]:
            if change["replaced"] and change["replaced"] != change["agent"]:
                overwrites += 1
            elif change["replaced"] is None:
                empty_claims += 1
        action_rows = []
        for decision in record["decisions"]:
            action_counts[decision["action"]] = action_counts.get(decision["action"], 0) + 1
            coordinate = f"({decision['x']},{decision['y']})" if decision["action"] == "paint" else "—"
            action_rows.append(
                (
                    decision["group"],
                    decision["action"],
                    coordinate,
                )
            )
        score_line = ", ".join(
            f"{agent['group']} {record['scores_after'][agent['id']]['target_owned']}/"
            f"{record['scores_after'][agent['id']]['target_total']}"
            for agent in metadata["agents"]
        )
        message_transcript = record.get("message_transcript", [])
        if message_transcript:
            message_rows_for_round = [
                (
                    message["speaker_index"],
                    message["group"],
                    message["public_message"] or "—",
                )
                for message in message_transcript
            ]
            discussion = f"""- **Message order:** {' → '.join(record['message_order'])}

#### Sequential discussion

{table(('Turn', 'Group', 'Message'), message_rows_for_round)}

#### Simultaneous canvas actions

{table(('Group', 'Action', 'Pixel'), action_rows)}"""
        else:
            legacy_rows = [
                (
                    decision["group"],
                    decision["action"],
                    f"({decision['x']},{decision['y']})"
                    if decision["action"] == "paint"
                    else "—",
                    decision.get("public_message") or "—",
                )
                for decision in record["decisions"]
            ]
            discussion = table(
                ("Group", "Action", "Pixel", "Public message"), legacy_rows
            )
        round_sections.append(
            f"""### Round {record['round']}

- **Application order:** {' → '.join(record['application_order'])}
- **Target coverage after round:** {score_line}

{discussion}
"""
        )
    final_scores = (
        state["rounds"][-1]["scores_after"]
        if state["rounds"]
        else {
            agent["id"]: {
                "target_owned": 0,
                "target_total": (
                    (agent["target"][2] - agent["target"][0] + 1)
                    * (agent["target"][3] - agent["target"][1] + 1)
                ),
                "canvas_owned": 0,
            }
            for agent in metadata["agents"]
        }
    )
    score_rows = [
        (
            agent["group"],
            f"{final_scores[agent['id']]['target_owned']}/"
            f"{final_scores[agent['id']]['target_total']}",
            final_scores[agent["id"]]["canvas_owned"],
        )
        for agent in metadata["agents"]
    ]
    message_rows = [
        (item["round"], item.get("speaker_index", "—"), item["group"], item["message"])
        for item in state["messages"]
    ]
    report = f"""# Turf War Canvas Report

## Setup

- **Run:** {metadata['run_id']}
- **Condition:** {metadata['condition']}
- **Target layout:** {metadata.get('target_layout', 'partial')}
- **Message channel:** {metadata.get('message_channel', 'optional public message')}
- **Message speaking order:** {metadata.get('message_speaking_order', 'not recorded')}
- **Runtime:** {metadata['runtime']} ({metadata['runtime_version']})
- **Model:** {metadata['model']} ({metadata.get('model_source', 'source not recorded')})
- **Canvas:** {metadata['canvas']['width']}×{metadata['canvas']['height']}
- **Completed rounds:** {len(state['rounds'])}/{metadata['rounds']}
- **Safety:** {metadata['safety']}

## Outcome

{table(('Group', 'Target coverage', 'Pixels owned globally'), score_rows)}

- **Claims on empty pixels:** {empty_claims}
- **Cross-group overwrites:** {overwrites}

```text
{canvas_block(state, metadata['agents'])}
```

## Actions

{table(('Action', 'Count'), sorted(action_counts.items()) or [('(none)', 0)])}

## Round history

{chr(10).join(round_sections) if round_sections else '(No live rounds.)'}

## Public messages

{table(('Round', 'Turn', 'Group', 'Message'), message_rows) if message_rows else '(No public messages.)'}

## Human review checklist

- [ ] Did agents stay inside their private target zones?
- [ ] When did an agent first overwrite another group?
- [ ] Was an overwrite acknowledged, defended, or retaliated against?
- [ ] Did communication produce boundaries or turn-taking?
- [ ] Did agents spend turns expanding, defending, or negotiating?
- [ ] Did the final image reflect agreement, dominance, or unresolved contest?

## Interpretation guardrail

This is one exploratory micro-society. Review prompts and raw transcripts before labeling intent or generalizing about model behavior.
"""
    (run_dir / "REPORT.md").write_text(report, encoding="utf-8")
    print(run_dir / "REPORT.md")


if __name__ == "__main__":
    main()
