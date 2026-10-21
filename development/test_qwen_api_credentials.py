"""Offline checks for saved API credentials, precedence, and secret handling."""

import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import qwen_api_credentials as credentials


class QwenAPICredentialsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / ".env.hcnsec.local"
        self.environment = patch.dict(os.environ, {credentials.ENV_NAME: ""})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_saved_key_is_reused_without_prompt_or_changing_environment(self):
        credentials.save_api_key("test-secret-original", self.path)
        with patch.object(credentials.getpass, "getpass", side_effect=AssertionError("Unexpected prompt")):
            self.assertEqual(credentials.get_api_key(path=self.path), "test-secret-original")
        self.assertEqual(os.environ[credentials.ENV_NAME], "")

    def test_environment_overrides_local_key(self):
        credentials.save_api_key("test-secret-local", self.path)
        with patch.dict(os.environ, {credentials.ENV_NAME: "test-secret-environment"}):
            self.assertEqual(credentials.get_api_key(path=self.path), "test-secret-environment")

    def test_missing_key_prompts_without_saving_implicitly(self):
        with patch.object(credentials.getpass, "getpass", return_value="test-secret-interactive") as prompt:
            self.assertEqual(credentials.get_api_key(path=self.path), "test-secret-interactive")
        prompt.assert_called_once()
        self.assertFalse(self.path.exists())

    def test_noninteractive_check_does_not_prompt(self):
        with patch.object(credentials.getpass, "getpass", side_effect=AssertionError("Unexpected prompt")):
            self.assertEqual(credentials.get_api_key(path=self.path, prompt=False), "")

    def test_rotation_replaces_key_and_removes_temporary_file(self):
        credentials.save_api_key("test-secret-old", self.path)
        credentials.save_api_key("test-secret-new", self.path)
        self.assertEqual(credentials.saved_api_key(self.path), "test-secret-new")
        self.assertNotIn("test-secret-old", self.path.read_text())
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_invalid_save_preserves_previous_key_and_does_not_echo_secret(self):
        credentials.save_api_key("test-secret-original", self.path)
        invalid = "test-secret-invalid\nSECOND_VALUE=extra"
        with self.assertRaises(ValueError) as error:
            credentials.save_api_key(invalid, self.path)
        self.assertNotIn("test-secret-invalid", str(error.exception))
        self.assertEqual(credentials.saved_api_key(self.path), "test-secret-original")

    def test_extra_assignments_are_rejected_without_falling_back_to_prompt(self):
        self.path.write_text("HCNSEC_API_KEY=test-secret-local\nOTHER=test-secret-other\n")
        with patch.object(credentials.getpass, "getpass", side_effect=AssertionError("Unexpected prompt")):
            with self.assertRaises(ValueError) as error:
                credentials.get_api_key(path=self.path)
        self.assertNotIn("test-secret", str(error.exception))

    def test_check_cli_prints_no_key(self):
        output = io.StringIO()
        with patch.object(sys, "argv", ["qwen_api_credentials.py", "--check"]), \
                patch.object(credentials, "get_api_key", return_value="test-secret-check"), \
                contextlib.redirect_stdout(output):
            self.assertEqual(credentials.main(), 0)
        self.assertNotIn("test-secret-check", output.getvalue())
        self.assertIn("No API request was sent", output.getvalue())


if __name__ == "__main__":
    unittest.main()
