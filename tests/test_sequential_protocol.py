import argparse
import asyncio
import json
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_experiment as experiment
import run_batch


class SequentialProtocolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.original_agents = experiment.AGENTS
        experiment.AGENTS = experiment.FULL_OVERLAP_AGENTS

    def tearDown(self) -> None:
        experiment.AGENTS = self.original_agents

    def test_messages_are_sequential_and_actions_share_the_full_transcript(self) -> None:
        message_visibility = []
        action_visibility = []

        async def fake_message(
            agent, args, run_dir, round_number, state, messages, speaker_index
        ):
            message_visibility.append((agent["id"], len(messages)))
            return {
                "agent": agent["id"],
                "group": agent["group"],
                "round": round_number,
                "speaker_index": speaker_index,
                "public_message": f"message-{speaker_index}",
            }

        async def fake_action(
            agent, args, run_dir, round_number, state, messages, delay
        ):
            action_visibility.append((agent["id"], len(messages), id(state)))
            return {
                "agent": agent["id"],
                "group": agent["group"],
                "round": round_number,
                "action": "pass",
                "x": 0,
                "y": 0,
            }

        args = argparse.Namespace(condition="blind", max_stagger=0)
        state = experiment.initial_state()
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(experiment, "call_message", fake_message), patch.object(
                experiment, "call_action", fake_action
            ):
                decisions, transcript = asyncio.run(
                    experiment.run_round(
                        args, Path(temp_dir), 1, state, random.Random(17)
                    )
                )

        self.assertEqual([visible for _, visible in message_visibility], [0, 1, 2])
        self.assertEqual([message["speaker_index"] for message in transcript], [1, 2, 3])
        self.assertEqual({agent for agent, _, _ in action_visibility}, {"amber", "blue", "green"})
        self.assertEqual({visible for _, visible, _ in action_visibility}, {3})
        self.assertEqual(len({snapshot_id for _, _, snapshot_id in action_visibility}), 1)
        self.assertEqual(len(decisions), 3)

        record = experiment.apply_round(state, decisions, transcript, random.Random(19))
        self.assertEqual(record["message_order"], [message["group"] for message in transcript])
        self.assertEqual([item["speaker_index"] for item in state["messages"]], [1, 2, 3])
        self.assertIn("Message order:", experiment.public_history(state))

    def test_message_and_action_schemas_are_separate(self) -> None:
        message_schema = json.loads(experiment.MESSAGE_SCHEMA.read_text(encoding="utf-8"))
        action_schema = json.loads(experiment.ACTION_SCHEMA.read_text(encoding="utf-8"))

        self.assertEqual(message_schema["required"], ["public_message"])
        self.assertNotIn("action", message_schema["properties"])
        self.assertEqual(action_schema["required"], ["action", "x", "y"])
        self.assertNotIn("public_message", action_schema["properties"])

    def test_prompts_assign_identity_and_require_direct_first_person_speech(self) -> None:
        state = experiment.initial_state()
        agent = experiment.FULL_OVERLAP_AGENTS[0]

        message_prompt = experiment.make_message_prompt(
            agent, "blind", 1, state, [], 1
        )
        action_prompt = experiment.make_action_prompt(agent, "blind", 1, state, [])

        self.assertIn("You are Amber, one of three groups", message_prompt)
        self.assertIn("Speak on your own behalf as Amber", message_prompt)
        self.assertIn('using first-person language such as "I" or "we"', message_prompt)
        self.assertIn("Do not narrate yourself from the outside", message_prompt)
        self.assertIn("Amber in the third person", message_prompt)
        self.assertIn("You are Amber, one of three groups", action_prompt)
        self.assertNotIn("You represent the Amber group", message_prompt)

    def test_randomizer_resume_matches_uninterrupted_round_boundaries(self) -> None:
        seed = 20260820
        uninterrupted = random.Random(seed)
        for _ in range(7):
            speaking_order = list(experiment.AGENTS)
            uninterrupted.shuffle(speaking_order)
            for _agent in experiment.AGENTS:
                uninterrupted.uniform(0, 1)
            application_order = list(experiment.AGENTS)
            uninterrupted.shuffle(application_order)

        resumed = random.Random(seed)
        experiment.advance_randomizer(resumed, 7)
        self.assertEqual(uninterrupted.getstate(), resumed.getstate())

    def test_custom_agents_are_loaded_and_validated(self) -> None:
        agents = [
            {"id": "one", "group": "One", "mark": "1", "target": [0, 0, 1, 1]},
            {"id": "two", "group": "Two", "mark": "2", "target": [1, 1, 2, 2]},
            {"id": "three", "group": "Three", "mark": "3", "target": [2, 2, 3, 3]},
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "agents.json"
            path.write_text(json.dumps(agents), encoding="utf-8")
            self.assertEqual(experiment.load_agents(path), tuple(agents))

    def test_batch_validator_requires_complete_clean_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            metadata = {
                "rounds": 1,
                "completed_at": "2026-08-18T00:00:00-07:00",
                "condition": "blind",
                "target_layout": "full",
            }
            state = {"rounds": [{"round": 1}]}
            (run_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
            (run_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
            clean = {
                "round": 1,
                "timed_out": False,
                "parse_error": None,
                "return_code": 0,
            }
            records = "".join(json.dumps(clean) + "\n" for _ in range(3))
            (run_dir / "messages.jsonl").write_text(records, encoding="utf-8")
            (run_dir / "decisions.jsonl").write_text(records, encoding="utf-8")

            valid, problems = run_batch.validate_run(run_dir, 1)
            self.assertTrue(valid, problems)

            bad_message = clean | {
                "group": "Amber",
                "public_message": "I will cooperate.\u0019",
            }
            bad_records = json.dumps(bad_message) + "\n" + "".join(
                json.dumps(clean) + "\n" for _ in range(2)
            )
            (run_dir / "messages.jsonl").write_text(bad_records, encoding="utf-8")
            valid, problems = run_batch.validate_run(run_dir, 1)
            self.assertFalse(valid)
            self.assertIn("control-character messages=1", problems)

            (run_dir / "messages.jsonl").write_text("", encoding="utf-8")
            valid, problems = run_batch.validate_run(run_dir, 1)
            self.assertFalse(valid)
            self.assertIn("messages=0", problems)


if __name__ == "__main__":
    unittest.main()
