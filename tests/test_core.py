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
        self.assertEqual(record.meeting_heading(["Weekly", "Standup"]), "Weekly Standup")

    def test_generated_filename_is_sanitized(self):
        self.assertEqual(
            record.sanitize_filename("Roadmap / Risks: Q3"),
            "Roadmap - Risks- Q3",
        )

    def test_numbering_uses_highest_existing_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "01 First.md").touch()
            (folder / "03 Third.md").touch()
            (folder / "unrelated.md").touch()
            self.assertEqual(record._next_meeting_number(folder), 4)

    def test_empty_vault_can_be_selected_as_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            picker = FolderPicker(Path(tmp))
            picker.completed = True
            picker.vault_root = True
            self.assertEqual(picker.get_destination(), Path(tmp))


class LlmCompatibilityTest(unittest.TestCase):
    @patch("llm.litellm.completion")
    def test_common_parameters_do_not_force_provider_specific_thinking(self, completion):
        completion.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Notes"))]
        )
        self.assertEqual(llm._call_llm("System", "Transcript"), "Notes")
        kwargs = completion.call_args.kwargs
        self.assertNotIn("thinking", kwargs)
        self.assertNotIn("allowed_openai_params", kwargs)
        self.assertNotIn("temperature", kwargs)


if __name__ == "__main__":
    unittest.main()
