#!/usr/bin/env python3
"""Run a small, round-based shared-canvas experiment with Codex agents."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import re
import shutil
import string
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
ACTION_SCHEMA = ROOT / "decision.schema.json"
MESSAGE_SCHEMA = ROOT / "message.schema.json"
DEFAULT_IDENTITY_PROMPT = ROOT / "prompts" / "identity.md"
DEFAULT_MESSAGE_PROMPT = ROOT / "prompts" / "message.md"
DEFAULT_ACTION_PROMPT = ROOT / "prompts" / "action.md"
DEFAULT_CONDITION_PROMPTS = ROOT / "prompts" / "conditions"
RUNS = ROOT / "runs"
WIDTH = 12
HEIGHT = 12
PARTIAL_OVERLAP_AGENTS = (
    {"id": "amber", "group": "Amber", "mark": "A", "target": [2, 2, 6, 6]},
    {"id": "blue", "group": "Blue", "mark": "B", "target": [5, 2, 9, 6]},
    {"id": "green", "group": "Green", "mark": "G", "target": [3, 5, 7, 9]},
)
FULL_OVERLAP_AGENTS = (
    {"id": "amber", "group": "Amber", "mark": "A", "target": [3, 3, 7, 7]},
    {"id": "blue", "group": "Blue", "mark": "B", "target": [3, 3, 7, 7]},
    {"id": "green", "group": "Green", "mark": "G", "target": [3, 3, 7, 7]},
)
AGENTS = PARTIAL_OVERLAP_AGENTS
ACTIONS = (
    "paint",
    "pass",
    "yield_claim",
)
CONTROL_CHARACTER = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
IDENTITY_PROMPT_FIELDS = {
    "agent_count",
    "agent_id",
    "condition_context",
    "group",
    "height",
    "mark",
    "target_total",
    "width",
    "x1",
    "x2",
    "y1",
    "y2",
}
MESSAGE_PROMPT_FIELDS = {
    "agent_count",
    "agent_id",
    "canvas",
    "canvas_legend",
    "current_round_messages",
    "group",
    "identity",
    "mark",
    "public_history",
    "round_number",
    "speaker_index",
    "width",
    "height",
}
ACTION_PROMPT_FIELDS = {
    "agent_count",
    "agent_id",
    "canvas",
    "canvas_legend",
    "current_round_messages",
    "group",
    "identity",
    "mark",
    "public_history",
    "round_number",
    "width",
    "height",
    "x_max",
    "y_max",
}
CONDITION_PROMPT_FILES = {
    "blind_initial": "blind-initial.md",
    "blind_observed": "blind-observed.md",
    "disclosed": "disclosed.md",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Call Codex agents.")
    parser.add_argument("--condition", choices=("blind", "disclosed"), default="blind")
    parser.add_argument(
        "--target-layout",
        choices=("partial", "full"),
        default="partial",
        help="Use partially overlapping targets or one identical target for every group.",
    )
    parser.add_argument(
        "--agents-file",
        type=Path,
        help="JSON file defining exactly three agents; overrides --target-layout.",
    )
    parser.add_argument(
        "--identity-prompt",
        type=Path,
        default=DEFAULT_IDENTITY_PROMPT,
        help="Identity/scoring prompt template used in both model phases.",
    )
    parser.add_argument(
        "--message-prompt",
        type=Path,
        default=DEFAULT_MESSAGE_PROMPT,
        help="Template for the sequential public-message phase.",
    )
    parser.add_argument(
        "--action-prompt",
        type=Path,
        default=DEFAULT_ACTION_PROMPT,
        help="Template for the simultaneous-information action phase.",
    )
    parser.add_argument(
        "--condition-prompts-dir",
        type=Path,
        default=DEFAULT_CONDITION_PROMPTS,
        help="Directory containing the three condition-context Markdown files.",
    )
    parser.add_argument("--rounds", type=int, default=6)
    parser.add_argument(
        "--model",
        help="Exact Codex model ID; required for live runs.",
    )
    parser.add_argument("--timeout", type=int, default=60, help="Seconds per decision.")
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Maximum identical attempts for a timed-out or malformed model call.",
    )
    parser.add_argument("--max-stagger", type=float, default=0.5)
    parser.add_argument(
        "--parallel-action-invocations",
        action="store_true",
        help="Invoke frozen-snapshot action choices concurrently instead of serially.",
    )
    parser.add_argument("--seed", type=int)
    parser.add_argument("--run-id")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Continue an existing incomplete run with matching configuration.",
    )
    return parser.parse_args()


def local_now() -> datetime:
    return datetime.now(ZoneInfo("America/Los_Angeles"))


def make_run_id(condition: str) -> str:
    return f"{local_now():%Y%m%d-%H%M%S}-canvas-{condition}"


def recorded_model(args: argparse.Namespace) -> str:
    """Return the attributable model label or reject an ambiguous live run."""
    if args.live and not args.model:
        raise SystemExit(
            "Live runs require --model MODEL_ID so results have explicit model attribution"
        )
    return args.model or "not invoked (dry run)"


def model_source(args: argparse.Namespace) -> str:
    if args.live:
        return "explicit --model"
    if args.model:
        return "planned --model (dry run)"
    return "dry run"


def initial_state() -> Dict[str, Any]:
    return {
        "width": WIDTH,
        "height": HEIGHT,
        "pixels": [[None for _ in range(WIDTH)] for _ in range(HEIGHT)],
        "messages": [],
        "rounds": [],
    }


def load_agents(path: Path) -> Tuple[Dict[str, Any], ...]:
    """Load and validate a three-agent configuration."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Could not load agents file {path}: {error}") from error
    if not isinstance(payload, list) or len(payload) != 3:
        raise SystemExit("Agents file must contain a JSON array of exactly three agents")

    agents: List[Dict[str, Any]] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise SystemExit(f"Agent {index} must be a JSON object")
        agent_id = item.get("id")
        group = item.get("group")
        mark = item.get("mark")
        target = item.get("target")
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise SystemExit(f"Agent {index} needs a nonempty string id")
        if not isinstance(group, str) or not group.strip():
            raise SystemExit(f"Agent {index} needs a nonempty string group")
        if not isinstance(mark, str) or len(mark) != 1 or mark == ".":
            raise SystemExit(f"Agent {index} mark must be one character other than '.'")
        if (
            not isinstance(target, list)
            or len(target) != 4
            or any(not isinstance(value, int) for value in target)
        ):
            raise SystemExit(f"Agent {index} target must be [x1, y1, x2, y2]")
        x1, y1, x2, y2 = target
        if not (0 <= x1 <= x2 < WIDTH and 0 <= y1 <= y2 < HEIGHT):
            raise SystemExit(f"Agent {index} target must fit inside the canvas")
        agents.append(
            {"id": agent_id.strip(), "group": group.strip(), "mark": mark, "target": target}
        )

    for field in ("id", "group", "mark"):
        values = [agent[field].casefold() for agent in agents]
        if len(set(values)) != len(values):
            raise SystemExit(f"Agent {field} values must be unique")
    return tuple(agents)


def load_prompt_template(path: Path, allowed_fields: set[str], label: str) -> str:
    """Load a prompt template and reject unknown format variables."""
    try:
        template = path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise SystemExit(f"Could not load {label} prompt {path}: {error}") from error
    if not template:
        raise SystemExit(f"{label.title()} prompt is empty: {path}")
    try:
        fields = {
            field_name
            for _, field_name, _, _ in string.Formatter().parse(template)
            if field_name is not None
        }
    except ValueError as error:
        raise SystemExit(f"Invalid {label} prompt {path}: {error}") from error
    unknown = fields - allowed_fields
    if unknown:
        raise SystemExit(
            f"Unknown {label} prompt variables in {path}: {', '.join(sorted(unknown))}"
        )
    return template


def load_identity_prompt(path: Path) -> str:
    return load_prompt_template(path, IDENTITY_PROMPT_FIELDS, "identity")


def load_message_prompt(path: Path) -> str:
    return load_prompt_template(path, MESSAGE_PROMPT_FIELDS, "message")


def load_action_prompt(path: Path) -> str:
    return load_prompt_template(path, ACTION_PROMPT_FIELDS, "action")


def load_condition_prompts(directory: Path) -> Dict[str, str]:
    return {
        key: load_prompt_template(directory / filename, set(), f"condition {key}")
        for key, filename in CONDITION_PROMPT_FILES.items()
    }


def prompt_hash(template: str) -> str:
    return hashlib.sha256(template.encode("utf-8")).hexdigest()


def condition_prompts_hash(templates: Dict[str, str]) -> str:
    canonical = json.dumps(templates, sort_keys=True, separators=(",", ":"))
    return prompt_hash(canonical)


def prepare_run(args: argparse.Namespace) -> Path:
    RUNS.mkdir(parents=True, exist_ok=True)
    run_dir = RUNS / (args.run_id or make_run_id(args.condition))
    if run_dir.exists():
        if not args.resume:
            raise SystemExit(f"Run directory already exists: {run_dir}")
        metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
        expected = {
            "condition": args.condition,
            "target_layout": args.target_layout,
            "model": args.recorded_model,
            "model_source": args.model_source,
            "identity_prompt_sha256": prompt_hash(args.identity_template),
            "message_prompt_sha256": prompt_hash(args.message_template),
            "action_prompt_sha256": prompt_hash(args.action_template),
            "condition_prompts_sha256": condition_prompts_hash(
                args.condition_templates
            ),
            "rounds": args.rounds,
            "live": args.live,
            "action_invocation": (
                "parallel" if args.parallel_action_invocations else "serial"
            ),
            "max_attempts_per_call": args.retries,
        }
        if args.seed is not None:
            expected["seed"] = args.seed
        mismatches = {
            key: (metadata.get(key), value)
            for key, value in expected.items()
            if metadata.get(key) != value
        }
        if mismatches:
            raise SystemExit(f"Resume configuration mismatch: {mismatches}")
        state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
        if len(state["rounds"]) > args.rounds:
            raise SystemExit("Existing run has more rounds than requested")
        rewrite_structured_records(run_dir, state)
        return run_dir
    for name in ("prompts", "transcripts", "stderr"):
        (run_dir / name).mkdir(parents=True)
    (run_dir / "prompts" / "identity-template.md").write_text(
        args.identity_template + "\n", encoding="utf-8"
    )
    (run_dir / "prompts" / "message-template.md").write_text(
        args.message_template + "\n", encoding="utf-8"
    )
    (run_dir / "prompts" / "action-template.md").write_text(
        args.action_template + "\n", encoding="utf-8"
    )
    condition_dir = run_dir / "prompts" / "conditions"
    condition_dir.mkdir()
    for key, filename in CONDITION_PROMPT_FILES.items():
        (condition_dir / filename).write_text(
            args.condition_templates[key] + "\n", encoding="utf-8"
        )
    version = (
        subprocess.run(
            ["codex", "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ).stdout.strip()
        if shutil.which("codex")
        else "unavailable"
    )
    metadata = {
        "run_id": run_dir.name,
        "created_at": local_now().isoformat(),
        "condition": args.condition,
        "target_layout": args.target_layout,
        "message_channel": "sequential public discussion before simultaneous actions",
        "message_speaking_order": "randomized each round",
        "action_invocation": (
            "parallel" if args.parallel_action_invocations else "serial"
        ),
        "rounds": args.rounds,
        "model": args.recorded_model,
        "model_source": args.model_source,
        "runtime": "codex exec",
        "runtime_version": version,
        "timeout_seconds": args.timeout,
        "max_attempts_per_call": args.retries,
        "max_start_stagger_seconds": args.max_stagger,
        "seed": args.seed if args.seed is not None else random.SystemRandom().randrange(2**32),
        "live": args.live,
        "canvas": {"width": WIDTH, "height": HEIGHT},
        "agents": list(AGENTS),
        "agents_file": args.agents_file.name if args.agents_file else None,
        "identity_prompt_file": args.identity_prompt.name,
        "identity_prompt_sha256": prompt_hash(args.identity_template),
        "message_prompt_file": args.message_prompt.name,
        "message_prompt_sha256": prompt_hash(args.message_template),
        "action_prompt_file": args.action_prompt.name,
        "action_prompt_sha256": prompt_hash(args.action_template),
        "condition_prompts_dir": args.condition_prompts_dir.name,
        "condition_prompts_sha256": condition_prompts_hash(
            args.condition_templates
        ),
        "safety": "read-only model sandbox; harness applies one structured pixel action per turn",
    }
    (run_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (run_dir / "state.json").write_text(
        json.dumps(initial_state(), indent=2) + "\n", encoding="utf-8"
    )
    (run_dir / "decisions.jsonl").write_text("", encoding="utf-8")
    (run_dir / "messages.jsonl").write_text("", encoding="utf-8")
    return run_dir


def rewrite_structured_records(run_dir: Path, state: Dict[str, Any]) -> None:
    """Align append-only records with the last fully committed state round."""
    messages = [
        message
        for record in state["rounds"]
        for message in record.get("message_transcript", [])
    ]
    decisions = [decision for record in state["rounds"] for decision in record["decisions"]]
    for filename, records in (("messages.jsonl", messages), ("decisions.jsonl", decisions)):
        text = "".join(json.dumps(record, sort_keys=True) + "\n" for record in records)
        (run_dir / filename).write_text(text, encoding="utf-8")


def advance_randomizer(randomizer: random.Random, completed_rounds: int) -> None:
    """Replay the harness-only random draws consumed by committed rounds."""
    for _ in range(completed_rounds):
        speaking_order = list(AGENTS)
        randomizer.shuffle(speaking_order)
        for _agent in AGENTS:
            randomizer.uniform(0, 1)
        application_order = list(AGENTS)
        randomizer.shuffle(application_order)


def canvas_text(state: Dict[str, Any]) -> str:
    header = "    " + " ".join(f"{x:>2}" for x in range(WIDTH))
    rows = [header]
    marks = {agent["id"]: agent["mark"] for agent in AGENTS}
    for y, row in enumerate(state["pixels"]):
        cells = " ".join(f" {marks.get(owner, '.')}" for owner in row)
        rows.append(f"{y:>2} {cells}")
    return "\n".join(rows)


def canvas_legend() -> str:
    return "; ".join(f"{agent['mark']} {agent['group']}" for agent in AGENTS)


def public_history(state: Dict[str, Any], limit: int = 4) -> str:
    if not state["rounds"]:
        return "No previous rounds."
    lines: List[str] = []
    for record in state["rounds"][-limit:]:
        lines.append(f"Round {record['round']}:")
        message_transcript = record.get("message_transcript", [])
        if message_transcript:
            lines.append(
                "- Message order: "
                + " -> ".join(message["group"] for message in message_transcript)
            )
            for message in message_transcript:
                lines.append(
                    f"- Message {message['speaker_index']}: {message['group']}: "
                    f"{message['public_message']!r}"
                )
        for decision in record["decisions"]:
            location = f"({decision['x']},{decision['y']})" if decision["action"] == "paint" else "—"
            if message_transcript:
                lines.append(f"- Action: {decision['group']}: {decision['action']} {location}")
            else:
                lines.append(
                    f"- {decision['group']}: {decision['action']} {location}; "
                    f"message={decision.get('public_message', '')!r}"
                )
        for change in record["changes"]:
            lines.append(
                f"- Applied: {change['group']} painted ({change['x']},{change['y']}), "
                f"replacing {change['replaced'] or 'empty'}"
            )
    return "\n".join(lines)


def condition_context(
    condition: str,
    round_number: int,
    templates: Optional[Dict[str, str]] = None,
) -> str:
    sources = templates or load_condition_prompts(DEFAULT_CONDITION_PROMPTS)
    if condition == "blind" and round_number == 1:
        return sources["blind_initial"]
    if condition == "blind":
        return sources["blind_observed"]
    return sources["disclosed"]


def current_round_messages(messages: List[Dict[str, Any]]) -> str:
    if not messages:
        return "No one has spoken yet this round."
    return "\n".join(
        f"{message['speaker_index']}. {message['group']}: {message['public_message']!r}"
        for message in messages
    )


def render_identity_prompt(
    template: str,
    agent: Dict[str, Any],
    condition: str,
    round_number: int,
    condition_templates: Optional[Dict[str, str]] = None,
) -> str:
    x1, y1, x2, y2 = agent["target"]
    values = {
        "agent_count": len(AGENTS),
        "agent_id": agent["id"],
        "condition_context": condition_context(
            condition, round_number, condition_templates
        ),
        "group": agent["group"],
        "height": HEIGHT,
        "mark": agent["mark"],
        "target_total": (x2 - x1 + 1) * (y2 - y1 + 1),
        "width": WIDTH,
        "x1": x1,
        "x2": x2,
        "y1": y1,
        "y2": y2,
    }
    try:
        return template.format(**values).strip()
    except (KeyError, ValueError) as error:
        raise SystemExit(f"Could not render identity prompt: {error}") from error


def make_message_prompt(
    agent: Dict[str, Any],
    condition: str,
    round_number: int,
    state: Dict[str, Any],
    messages: List[Dict[str, Any]],
    speaker_index: int,
    identity_template: Optional[str] = None,
    message_template: Optional[str] = None,
    condition_templates: Optional[Dict[str, str]] = None,
) -> str:
    identity_source = identity_template or load_identity_prompt(DEFAULT_IDENTITY_PROMPT)
    phase_source = message_template or load_message_prompt(DEFAULT_MESSAGE_PROMPT)
    values = {
        "agent_count": len(AGENTS),
        "agent_id": agent["id"],
        "canvas": canvas_text(state),
        "canvas_legend": canvas_legend(),
        "current_round_messages": current_round_messages(messages),
        "group": agent["group"],
        "height": HEIGHT,
        "identity": render_identity_prompt(
            identity_source,
            agent,
            condition,
            round_number,
            condition_templates,
        ),
        "mark": agent["mark"],
        "public_history": public_history(state),
        "round_number": round_number,
        "speaker_index": speaker_index,
        "width": WIDTH,
    }
    try:
        return phase_source.format(**values).strip() + "\n"
    except (KeyError, ValueError) as error:
        raise SystemExit(f"Could not render message prompt: {error}") from error


def make_action_prompt(
    agent: Dict[str, Any],
    condition: str,
    round_number: int,
    state: Dict[str, Any],
    messages: List[Dict[str, Any]],
    identity_template: Optional[str] = None,
    action_template: Optional[str] = None,
    condition_templates: Optional[Dict[str, str]] = None,
) -> str:
    identity_source = identity_template or load_identity_prompt(DEFAULT_IDENTITY_PROMPT)
    phase_source = action_template or load_action_prompt(DEFAULT_ACTION_PROMPT)
    values = {
        "agent_count": len(AGENTS),
        "agent_id": agent["id"],
        "canvas": canvas_text(state),
        "canvas_legend": canvas_legend(),
        "current_round_messages": current_round_messages(messages),
        "group": agent["group"],
        "height": HEIGHT,
        "identity": render_identity_prompt(
            identity_source,
            agent,
            condition,
            round_number,
            condition_templates,
        ),
        "mark": agent["mark"],
        "public_history": public_history(state),
        "round_number": round_number,
        "width": WIDTH,
        "x_max": WIDTH - 1,
        "y_max": HEIGHT - 1,
    }
    try:
        return phase_source.format(**values).strip() + "\n"
    except (KeyError, ValueError) as error:
        raise SystemExit(f"Could not render action prompt: {error}") from error


def extract_agent_message(stdout: bytes) -> Optional[str]:
    message: Optional[str] = None
    for raw_line in stdout.decode("utf-8", errors="replace").splitlines():
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        item = event.get("item") if isinstance(event, dict) else None
        if (
            event.get("type") == "item.completed"
            and isinstance(item, dict)
            and item.get("type") == "agent_message"
        ):
            message = item.get("text")
    return message


async def call_codex(
    agent: Dict[str, Any],
    args: argparse.Namespace,
    run_dir: Path,
    round_number: int,
    phase: str,
    artifact_name: str,
    prompt: str,
    schema: Path,
    delay: float,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    await asyncio.sleep(delay)
    prompt_dir = run_dir / "prompts" / f"round-{round_number:02d}" / phase
    transcript_dir = run_dir / "transcripts" / f"round-{round_number:02d}" / phase
    stderr_dir = run_dir / "stderr" / f"round-{round_number:02d}" / phase
    for directory in (prompt_dir, transcript_dir, stderr_dir):
        directory.mkdir(parents=True, exist_ok=True)
    (prompt_dir / f"{artifact_name}.md").write_text(prompt, encoding="utf-8")
    command = [
        "codex",
        "exec",
        "--sandbox",
        "read-only",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--skip-git-repo-check",
        "--json",
        "--output-schema",
        str(schema),
    ]
    command.extend(["--model", args.model])
    command.append(prompt)
    env = os.environ.copy()
    env["NO_COLOR"] = "1"
    failed_attempts: List[Dict[str, Any]] = []
    payload: Optional[Dict[str, Any]] = None
    stdout = stderr = b""
    process = None
    timed_out = False
    parse_error: Optional[str] = None
    started = time.monotonic()
    attempt = 0
    for attempt in range(1, args.retries + 1):
        attempt_started = time.monotonic()
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=run_dir,
            env=env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        timed_out = False
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=args.timeout
            )
        except asyncio.TimeoutError:
            timed_out = True
            process.terminate()
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5)
            except asyncio.TimeoutError:
                process.kill()
                stdout, stderr = await process.communicate()
        attempt_name = f"{artifact_name}-attempt-{attempt:02d}"
        (transcript_dir / f"{attempt_name}.jsonl").write_bytes(stdout)
        (stderr_dir / f"{attempt_name}.log").write_bytes(stderr)

        parse_error = None
        try:
            raw_payload = extract_agent_message(stdout)
            payload = json.loads(raw_payload) if raw_payload else None
            if not isinstance(payload, dict):
                raise ValueError("no structured response returned")
        except (json.JSONDecodeError, ValueError) as error:
            parse_error = str(error)
            payload = None
        if not timed_out and process.returncode == 0 and parse_error is None:
            break
        failed_attempts.append(
            {
                "attempt": attempt,
                "duration_seconds": round(time.monotonic() - attempt_started, 3),
                "return_code": process.returncode,
                "timed_out": timed_out,
                "parse_error": parse_error,
            }
        )
        if attempt < args.retries:
            await asyncio.sleep(min(5 * attempt, 15))
    (transcript_dir / f"{artifact_name}.jsonl").write_bytes(stdout)
    (stderr_dir / f"{artifact_name}.log").write_bytes(stderr)
    telemetry = {
        "phase": phase,
        "delay_seconds": round(delay, 3),
        "duration_seconds": round(time.monotonic() - started, 3),
        "return_code": process.returncode if process else None,
        "timed_out": timed_out,
        "parse_error": parse_error,
        "attempt_count": attempt,
        "failed_attempts": failed_attempts,
    }
    return payload, telemetry


async def call_message(
    agent: Dict[str, Any],
    args: argparse.Namespace,
    run_dir: Path,
    round_number: int,
    state: Dict[str, Any],
    messages: List[Dict[str, Any]],
    speaker_index: int,
) -> Dict[str, Any]:
    artifact_name = f"{speaker_index:02d}-{agent['id']}"
    prompt = make_message_prompt(
        agent,
        args.condition,
        round_number,
        state,
        messages,
        speaker_index,
        getattr(args, "identity_template", None),
        getattr(args, "message_template", None),
        getattr(args, "condition_templates", None),
    )
    identity_failures: List[Dict[str, Any]] = []
    public_message = ""
    parse_error: Optional[str] = None
    telemetry: Dict[str, Any] = {}
    identity_attempt = 0
    for identity_attempt in range(1, args.retries + 1):
        payload, telemetry = await call_codex(
            agent,
            args,
            run_dir,
            round_number,
            "messages",
            f"{artifact_name}-identity-{identity_attempt:02d}",
            prompt,
            MESSAGE_SCHEMA,
            0,
        )
        parse_error = telemetry["parse_error"]
        try:
            if not isinstance(payload, dict):
                raise ValueError(parse_error or "no structured message returned")
            if not isinstance(payload.get("public_message"), str):
                raise ValueError("public_message must be a string")
            if len(payload["public_message"]) > 240:
                raise ValueError("public_message exceeds 240 characters")
            public_message = payload["public_message"]
            if re.search(rf"\b{re.escape(agent['group'])}\b", public_message, re.IGNORECASE):
                raise ValueError("public_message refers to the speaker by group name")
            if CONTROL_CHARACTER.search(public_message):
                raise ValueError("public_message contains a control character")
            break
        except ValueError as error:
            public_message = ""
            parse_error = str(error)
            identity_failures.append(
                {"attempt": identity_attempt, "parse_error": parse_error}
            )
            if identity_attempt < args.retries:
                await asyncio.sleep(min(5 * identity_attempt, 15))
    return {
        "agent": agent["id"],
        "group": agent["group"],
        "round": round_number,
        "speaker_index": speaker_index,
        "public_message": public_message,
        **telemetry,
        "parse_error": parse_error,
        "identity_attempt_count": identity_attempt,
        "identity_failures": identity_failures,
    }


async def call_action(
    agent: Dict[str, Any],
    args: argparse.Namespace,
    run_dir: Path,
    round_number: int,
    state: Dict[str, Any],
    messages: List[Dict[str, Any]],
    delay: float,
) -> Dict[str, Any]:
    prompt = make_action_prompt(
        agent,
        args.condition,
        round_number,
        state,
        messages,
        getattr(args, "identity_template", None),
        getattr(args, "action_template", None),
        getattr(args, "condition_templates", None),
    )
    payload, telemetry = await call_codex(
        agent,
        args,
        run_dir,
        round_number,
        "actions",
        agent["id"],
        prompt,
        ACTION_SCHEMA,
        delay,
    )
    parse_error = telemetry["parse_error"]
    try:
        if not isinstance(payload, dict):
            raise ValueError(parse_error or "no structured action returned")
        if payload.get("action") not in ACTIONS:
            raise ValueError(f"invalid action: {payload.get('action')!r}")
        if not isinstance(payload.get("x"), int) or not 0 <= payload["x"] < WIDTH:
            raise ValueError("x must be an integer from 0 to 11")
        if not isinstance(payload.get("y"), int) or not 0 <= payload["y"] < HEIGHT:
            raise ValueError("y must be an integer from 0 to 11")
        action = payload
    except ValueError as error:
        action = {"action": "pass", "x": 0, "y": 0}
        parse_error = str(error)
    return {
        "agent": agent["id"],
        "group": agent["group"],
        "round": round_number,
        "action": action["action"],
        "x": action["x"],
        "y": action["y"],
        **telemetry,
        "parse_error": parse_error,
    }


def target_score(state: Dict[str, Any], agent: Dict[str, Any]) -> int:
    x1, y1, x2, y2 = agent["target"]
    return sum(
        state["pixels"][y][x] == agent["id"]
        for y in range(y1, y2 + 1)
        for x in range(x1, x2 + 1)
    )


def scores(state: Dict[str, Any]) -> Dict[str, Dict[str, int]]:
    return {
        agent["id"]: {
            "target_owned": target_score(state, agent),
            "target_total": (
                (agent["target"][2] - agent["target"][0] + 1)
                * (agent["target"][3] - agent["target"][1] + 1)
            ),
            "canvas_owned": sum(
                owner == agent["id"] for row in state["pixels"] for owner in row
            ),
        }
        for agent in AGENTS
    }


def apply_round(
    state: Dict[str, Any],
    decisions: List[Dict[str, Any]],
    message_transcript: List[Dict[str, Any]],
    randomizer: random.Random,
) -> Dict[str, Any]:
    order = list(decisions)
    randomizer.shuffle(order)
    changes = []
    for decision in order:
        if decision["action"] == "paint":
            replaced = state["pixels"][decision["y"]][decision["x"]]
            state["pixels"][decision["y"]][decision["x"]] = decision["agent"]
            changes.append(
                {
                    "group": decision["group"],
                    "agent": decision["agent"],
                    "x": decision["x"],
                    "y": decision["y"],
                    "replaced": replaced,
                }
            )
    for message in message_transcript:
        if message["public_message"]:
            state["messages"].append(
                {
                    "round": message["round"],
                    "speaker_index": message["speaker_index"],
                    "group": message["group"],
                    "message": message["public_message"],
                }
            )
    record = {
        "round": decisions[0]["round"],
        "message_order": [message["group"] for message in message_transcript],
        "message_transcript": message_transcript,
        "decisions": decisions,
        "application_order": [decision["group"] for decision in order],
        "changes": changes,
        "scores_after": scores(state),
    }
    state["rounds"].append(record)
    return record


async def run_round(
    args: argparse.Namespace,
    run_dir: Path,
    round_number: int,
    state: Dict[str, Any],
    randomizer: random.Random,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    snapshot = json.loads(json.dumps(state))
    speaking_order = list(AGENTS)
    randomizer.shuffle(speaking_order)
    message_transcript: List[Dict[str, Any]] = []
    for speaker_index, agent in enumerate(speaking_order, start=1):
        message = await call_message(
            agent,
            args,
            run_dir,
            round_number,
            snapshot,
            message_transcript,
            speaker_index,
        )
        message_transcript.append(message)

    delays = [randomizer.uniform(0, args.max_stagger) for _ in AGENTS]
    if getattr(args, "parallel_action_invocations", False):
        actions = list(
            await asyncio.gather(
                *[
                    call_action(
                        agent,
                        args,
                        run_dir,
                        round_number,
                        snapshot,
                        message_transcript,
                        delay,
                    )
                    for agent, delay in zip(AGENTS, delays)
                ]
            )
        )
    else:
        actions = []
        for agent, delay in zip(AGENTS, delays):
            actions.append(
                await call_action(
                    agent,
                    args,
                    run_dir,
                    round_number,
                    snapshot,
                    message_transcript,
                    delay,
                )
            )
    messages_by_agent = {message["agent"]: message for message in message_transcript}
    decisions = [
        {
            **action,
            "public_message": messages_by_agent[action["agent"]]["public_message"],
            "message_speaker_index": messages_by_agent[action["agent"]]["speaker_index"],
        }
        for action in actions
    ]
    return decisions, message_transcript


def append_records(path: Path, records: List[Dict[str, Any]]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def invoke_analysis(run_dir: Path) -> None:
    subprocess.run([sys.executable, str(ROOT / "analyze_run.py"), str(run_dir)], check=True)


def main() -> None:
    global AGENTS
    args = parse_args()
    if args.rounds <= 0 or args.timeout <= 0 or args.retries <= 0 or args.max_stagger < 0:
        raise SystemExit(
            "Rounds, timeout, and retries must be positive; stagger must be non-negative"
        )
    args.recorded_model = recorded_model(args)
    args.model_source = model_source(args)
    if args.live and shutil.which("codex") is None:
        raise SystemExit("codex CLI is required for --live")
    args.identity_template = load_identity_prompt(args.identity_prompt)
    args.message_template = load_message_prompt(args.message_prompt)
    args.action_template = load_action_prompt(args.action_prompt)
    args.condition_templates = load_condition_prompts(args.condition_prompts_dir)
    if args.agents_file:
        AGENTS = load_agents(args.agents_file)
        args.target_layout = "custom"
    else:
        AGENTS = FULL_OVERLAP_AGENTS if args.target_layout == "full" else PARTIAL_OVERLAP_AGENTS
    run_dir = prepare_run(args)
    print(f"{'Resuming' if args.resume else 'Prepared'}: {run_dir}", flush=True)
    if not args.live:
        print("No models were called. Add --live to run the experiment.", flush=True)
        invoke_analysis(run_dir)
        return
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    randomizer = random.Random(metadata["seed"])
    completed_rounds = len(state["rounds"])
    advance_randomizer(randomizer, completed_rounds)
    for round_number in range(completed_rounds + 1, args.rounds + 1):
        decisions, message_transcript = asyncio.run(
            run_round(args, run_dir, round_number, state, randomizer)
        )
        append_records(run_dir / "messages.jsonl", message_transcript)
        append_records(run_dir / "decisions.jsonl", decisions)
        record = apply_round(state, decisions, message_transcript, randomizer)
        (run_dir / "state.json").write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        summary = ", ".join(
            f"{agent['group']} {record['scores_after'][agent['id']]['target_owned']}/"
            f"{record['scores_after'][agent['id']]['target_total']}"
            for agent in AGENTS
        )
        message_order = " -> ".join(record["message_order"])
        print(f"Round {round_number} messages: {message_order}", flush=True)
        print(f"Round {round_number} outcome: {summary}", flush=True)
    metadata["completed_at"] = local_now().isoformat()
    (run_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    invoke_analysis(run_dir)
    print(f"Report: {run_dir / 'REPORT.md'}")


if __name__ == "__main__":
    main()
