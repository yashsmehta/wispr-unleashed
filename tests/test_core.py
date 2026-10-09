import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import llm
import record
from ui import FolderPicker


class RecordingHelpersTest(unittest.TestCase):
    def test_requested_heading_is_used(self):
        self.assertEqual(
            record.meeting_heading(["Weekly", "Standup"]), "Weekly Standup"
        )

    def test_generated_filename_is_sanitized(self):
        self.assertEqual(
            record.sanitize_filename("Roadmap / Risks: Q3"),
            "Roadmap - Risks- Q3",
        )

    def test_filename_fallback_is_also_sanitized(self):
        self.assertEqual(record.sanitize_filename("", "Planning / Q3"), "Planning - Q3")

    def test_numbering_uses_highest_existing_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "01 First.md").touch()
            (folder / "03 Third.md").touch()
            (folder / "unrelated.md").touch()
            self.assertEqual(record._next_meeting_number(folder), 4)

    @patch("ui.tty.setcbreak")
    @patch("ui.termios.tcsetattr")
    @patch("ui.termios.tcgetattr", return_value=[])
    @patch("ui.SelectMenu.run", return_value="(vault root)")
    def test_empty_vault_can_be_selected_as_destination(self, *_mocks):
        with tempfile.TemporaryDirectory() as tmp:
            picker = FolderPicker(Path(tmp))
            self.assertEqual(picker.run(), Path(tmp))


class LlmCompatibilityTest(unittest.TestCase):
    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"})
    @patch("llm.subprocess.run")
    def test_calls_headless_claude_with_logged_in_account(self, run):
        run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"is_error": False, "result": "Notes\n\n\n\nMore"}),
            stderr="",
        )
        self.assertEqual(llm._call_llm("System", "Transcript"), "Notes\n\nMore")
        cmd = run.call_args.args[0]
        kwargs = run.call_args.kwargs
        self.assertIn("-p", cmd)
        self.assertEqual(cmd[cmd.index("--model") + 1], llm.CLAUDE_MODEL)
        self.assertEqual(cmd[cmd.index("--effort") + 1], llm.CLAUDE_EFFORT)
        self.assertEqual(cmd[cmd.index("--system-prompt") + 1], "System")
        self.assertEqual(kwargs["input"], "Transcript")
        self.assertNotIn("ANTHROPIC_API_KEY", kwargs["env"])

    @patch("llm._call_llm", return_value="Title\nBody")
    def test_generate_notes_makes_single_call_with_notes_prompt(self, call):
        self.assertEqual(llm.generate_notes("Transcript", 3), "Title\nBody")
        call.assert_called_once()
        prompt, transcript = call.call_args.args
        self.assertTrue(prompt.startswith(llm._read_prompt("notes")))
        self.assertEqual(transcript, "Transcript")

    @patch("llm.subprocess.run")
    def test_error_result_raises(self, run):
        run.return_value = SimpleNamespace(
            returncode=1,
            stdout=json.dumps({"is_error": True, "result": "Not logged in"}),
            stderr="",
        )
        with self.assertRaisesRegex(RuntimeError, "Not logged in"):
            llm._call_llm("System", "Transcript")


if __name__ == "__main__":
    unittest.main()
