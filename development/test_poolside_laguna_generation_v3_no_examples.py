from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import patch

import poolside_laguna_generation_v3_no_examples as profile


class RetrievalProjectionTests(unittest.TestCase):
    def test_removes_only_payload_examples_and_preserves_original(self):
        original_text = json.dumps({
            "title": "Boolean comparison",
            "vulnerability_type": "boolean-based blind",
            "detection_method": "Compare matched true and false conditions.",
            "payload_examples": [{"value": "example"}],
        })
        original = {"chunks": [{"chunk_id": "chunk-1", "text": original_text}]}

        projected, removed = profile.strip_payload_examples(original)

        self.assertEqual(removed, 1)
        self.assertEqual(json.loads(projected["chunks"][0]["text"]), {
            "title": "Boolean comparison",
            "vulnerability_type": "boolean-based blind",
            "detection_method": "Compare matched true and false conditions.",
        })
        self.assertIn("payload_examples", json.loads(original_text))

    def test_rejects_unstructured_retrieved_text(self):
        with self.assertRaisesRegex(ValueError, "not valid JSON"):
            profile.strip_payload_examples({"chunks": [{"chunk_id": "x", "text": "plain text"}]})

    def test_generation_callback_pins_profile_and_context_policy(self):
        captured = {}

        def base_factory(api, attempt_directory, scenario, retrieval, baseline, config):
            captured["retrieval"] = retrieval
            return lambda previous, attempted, retry_index, rejection_code: (
                {"payload": "candidate"}, {"prompt_version": "old"})

        retrieval = {"chunks": [{"chunk_id": "x", "text": json.dumps({
            "title": "Context", "payload_examples": [{"value": "do not send"}]})}]}
        with patch.object(profile.base_profile, "make_generation_callback", base_factory):
            callback = profile.make_generation_callback(
                object(), Path("attempt"), {}, retrieval, {}, {})
        _, audit = callback(None, [], 0, None)

        projected = json.loads(captured["retrieval"]["chunks"][0]["text"])
        self.assertNotIn("payload_examples", projected)
        self.assertEqual(audit["prompt_version"], profile.PROMPT_VERSION)
        self.assertEqual(audit["retrieval_context_policy_id"], profile.RETRIEVAL_CONTEXT_POLICY_ID)
        self.assertEqual(audit["payload_examples_removed_from_retrieved_chunks"], 1)


if __name__ == "__main__":
    unittest.main()
