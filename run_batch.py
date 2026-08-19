#!/usr/bin/env python3
"""Run and strictly validate a batch of independent canvas replications."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "runs"
DEFAULT_IDENTITY_PROMPT = ROOT / "prompts" / "identity.md"
LOGS = RUNS / "batch-logs"
EXCLUDED = RUNS / "excluded"
CONTROL_CHARACTER = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--start-seed", type=int, default=1)
    parser.add_argument("--condition", choices=("blind", "disclosed"), default="blind")
    parser.add_argument("--target-layout", choices=("partial", "full"), default="full")
    parser.add_argument(
        "--identity-prompt",
        type=Path,
        default=DEFAULT_IDENTITY_PROMPT,
        help="Identity/scoring prompt template forwarded to every replication.",
    )
    parser.add_argument("--prefix")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--model")
    return parser.parse_args()


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def validate_run(
    run_dir: Path,
    expected_rounds: int,
    expected_seed: int | None = None,
    expected_run_id: str | None = None,
    expected_condition: str = "blind",
    expected_target_layout: str = "full",
    expected_identity_prompt_sha256: str | None = None,
) -> Tuple[bool, List[str]]:
    problems: List[str] = []
    try:
        metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
        state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
        messages = load_jsonl(run_dir / "messages.jsonl")
        decisions = load_jsonl(run_dir / "decisions.jsonl")
    except (FileNotFoundError, json.JSONDecodeError) as error:
        return False, [str(error)]

    if not metadata.get("completed_at"):
        problems.append("missing completed_at")
    if metadata.get("rounds") != expected_rounds:
        problems.append(f"metadata rounds={metadata.get('rounds')}")
    if metadata.get("condition") != expected_condition:
        problems.append(f"condition={metadata.get('condition')}")
    if metadata.get("target_layout") != expected_target_layout:
        problems.append(f"target_layout={metadata.get('target_layout')}")
    if (
        expected_identity_prompt_sha256 is not None
        and metadata.get("identity_prompt_sha256") != expected_identity_prompt_sha256
    ):
        problems.append("identity prompt does not match the requested template")
    if expected_seed is not None and metadata.get("seed") != expected_seed:
        problems.append(f"seed={metadata.get('seed')}")
    if expected_run_id is not None and metadata.get("run_id") != expected_run_id:
        problems.append(f"run_id={metadata.get('run_id')}")
    if len(state.get("rounds", [])) != expected_rounds:
        problems.append(f"state rounds={len(state.get('rounds', []))}")
    expected_records = expected_rounds * 3
    if len(messages) != expected_records:
        problems.append(f"messages={len(messages)}")
    if len(decisions) != expected_records:
        problems.append(f"decisions={len(decisions)}")
    for label, records in (("message", messages), ("decision", decisions)):
        bad = [
            item
            for item in records
            if item.get("timed_out")
            or item.get("parse_error") is not None
            or item.get("return_code") != 0
        ]
        if bad:
            problems.append(f"{label} telemetry failures={len(bad)}")
    self_name_messages = [
        item
        for item in messages
        if item.get("group")
        and re.search(
            rf"\b{re.escape(str(item.get('group', '')))}\b",
            str(item.get("public_message", "")),
            re.IGNORECASE,
        )
    ]
    if self_name_messages:
        problems.append(f"third-person self-name messages={len(self_name_messages)}")
    control_character_messages = [
        item
        for item in messages
        if CONTROL_CHARACTER.search(str(item.get("public_message", "")))
    ]
    if control_character_messages:
        problems.append(f"control-character messages={len(control_character_messages)}")
    round_numbers = [record.get("round") for record in state.get("rounds", [])]
    if round_numbers != list(range(1, expected_rounds + 1)):
        problems.append("round sequence is incomplete or out of order")
    return not problems, problems


def manifest_entry(run_id: str, seed: int, status: str, **extra: Any) -> Dict[str, Any]:
    return {"run_id": run_id, "seed": seed, "status": status, **extra}


def archive_completed_invalid_run(run_dir: Path, problems: List[str]) -> Path:
    """Move a completed but invalid candidate aside without deleting its evidence."""
    EXCLUDED.mkdir(parents=True, exist_ok=True)
    attempt = 1
    while True:
        destination = EXCLUDED / f"{run_dir.name}-candidate-{attempt:02d}"
        if not destination.exists():
            break
        attempt += 1
    run_dir.rename(destination)
    exclusion = {
        "excluded_at": datetime.now(ZoneInfo("America/Los_Angeles")).isoformat(),
        "problems": problems,
    }
    (destination / "EXCLUSION.json").write_text(
        json.dumps(exclusion, indent=2) + "\n", encoding="utf-8"
    )
    log_path = LOGS / f"{run_dir.name}.log"
    if log_path.exists():
        log_path.rename(EXCLUDED / f"{destination.name}.log")
    return destination


async def run_one(
    args: argparse.Namespace,
    index: int,
    semaphore: asyncio.Semaphore,
) -> Dict[str, Any]:
    run_id = f"{args.prefix}-{index:02d}"
    seed = args.start_seed + index - 1
    run_dir = RUNS / run_id
    valid, problems = (
        validate_run(
            run_dir,
            args.rounds,
            seed,
            run_id,
            args.condition,
            args.target_layout,
            args.identity_prompt_sha256,
        )
        if run_dir.exists()
        else (False, [])
    )
    if valid:
        return manifest_entry(run_id, seed, "complete", skipped=True)

    archived_candidate: str | None = None
    if run_dir.exists():
        try:
            completed = bool(
                json.loads((run_dir / "metadata.json").read_text(encoding="utf-8")).get(
                    "completed_at"
                )
            )
        except (FileNotFoundError, json.JSONDecodeError):
            completed = False
        if completed:
            archived_candidate = str(archive_completed_invalid_run(run_dir, problems))

    command = [
        sys.executable,
        str(ROOT / "run_experiment.py"),
        "--live",
        "--condition",
        args.condition,
        "--target-layout",
        args.target_layout,
        "--identity-prompt",
        str(args.identity_prompt),
        "--rounds",
        str(args.rounds),
        "--timeout",
        str(args.timeout),
        "--max-stagger",
        "0.5",
        "--seed",
        str(seed),
        "--run-id",
        run_id,
    ]
    if run_dir.exists():
        command.append("--resume")
    if args.model:
        command.extend(["--model", args.model])

    LOGS.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    async with semaphore:
        with (LOGS / f"{run_id}.log").open("ab") as log:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=ROOT,
                stdout=log,
                stderr=asyncio.subprocess.STDOUT,
            )
            return_code = await process.wait()

    valid, problems = validate_run(
        run_dir,
        args.rounds,
        seed,
        run_id,
        args.condition,
        args.target_layout,
        args.identity_prompt_sha256,
    )
    return manifest_entry(
        run_id,
        seed,
        "complete" if valid else "failed",
        return_code=return_code,
        duration_seconds=round(time.monotonic() - started, 3),
        problems=problems,
        archived_candidate=archived_candidate,
    )


async def run_batch(args: argparse.Namespace) -> List[Dict[str, Any]]:
    if args.count <= 0 or args.concurrency <= 0 or args.rounds <= 0:
        raise SystemExit("count, concurrency, and rounds must be positive")
    semaphore = asyncio.Semaphore(args.concurrency)
    tasks = [asyncio.create_task(run_one(args, index, semaphore)) for index in range(1, args.count + 1)]
    results: List[Dict[str, Any]] = []
    for completed, task in enumerate(asyncio.as_completed(tasks), start=1):
        result = await task
        results.append(result)
        print(
            f"[{completed:02d}/{args.count:02d}] {result['run_id']}: {result['status']}",
            flush=True,
        )
    return sorted(results, key=lambda item: item["run_id"])


def main() -> None:
    args = parse_args()
    args.identity_prompt = args.identity_prompt.resolve()
    try:
        identity_prompt = args.identity_prompt.read_bytes()
    except OSError as error:
        raise SystemExit(f"Could not load identity prompt {args.identity_prompt}: {error}") from error
    args.identity_prompt_sha256 = hashlib.sha256(identity_prompt.strip()).hexdigest()
    if args.prefix is None:
        args.prefix = f"canvas-{args.condition}-{args.target_layout}-rep"
    results = asyncio.run(run_batch(args))
    manifest = {
        "created_at": datetime.now(ZoneInfo("America/Los_Angeles")).isoformat(),
        "configuration": {
            "count": args.count,
            "concurrency": args.concurrency,
            "rounds": args.rounds,
            "start_seed": args.start_seed,
            "prefix": args.prefix,
            "condition": args.condition,
            "target_layout": args.target_layout,
            "identity_prompt_file": args.identity_prompt.name,
            "identity_prompt_sha256": args.identity_prompt_sha256,
            "timeout_seconds": args.timeout,
            "model": args.model or "Codex default",
        },
        "runs": results,
    }
    manifest_path = RUNS / f"{args.prefix}-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    failed = [result for result in results if result["status"] != "complete"]
    print(f"Manifest: {manifest_path}", flush=True)
    if failed:
        raise SystemExit(f"{len(failed)} runs failed strict validation")


if __name__ == "__main__":
    main()
