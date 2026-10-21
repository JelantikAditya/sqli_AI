"""Offline checks for the API runner's adaptive-loop input adapter."""

import unittest
from pathlib import Path
import sys
import hashlib
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dvwa"))
sys.path.insert(0, str(ROOT / "development"))

import adaptive_candidate_policy
from run_qwen_api_experiments import (copy_verified_index_snapshot,
                                     normalize_observation_candidate,
                                     store_file_hashes)


class ObservationCandidateAdapterTests(unittest.TestCase):
    def test_s1_payload_string_is_wrapped_for_adaptive_observation(self):
        candidate = normalize_observation_candidate("1'", "S1")

        self.assertEqual(candidate, {"payload": "1'"})
        self.assertEqual(len(adaptive_candidate_policy.candidate_key(candidate, "single_error")), 64)

    def test_non_s1_candidate_shape_is_preserved(self):
        candidate = {"true_payload": "1 OR 1=1", "false_payload": "1 OR 1=2"}

        self.assertIs(normalize_observation_candidate(candidate, "S2"), candidate)

    def test_retrieval_copy_keeps_the_pinned_source_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "data" / "vectorstore" / "snapshot"
            source.mkdir(parents=True)
            (source / "manifest.json").write_text("{}", encoding="utf-8")
            (source / "data_level0.bin").write_bytes(b"approved-index")
            approved = {
                path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in source.rglob("*") if path.is_file()
            }

            record = copy_verified_index_snapshot(
                {"resolved_store_path": str(source)}, {"index_file_sha256": approved},
                root / "results" / "retrieval-copy", root)
            copy = root / record["copy_store_path"]
            (copy / "data_level0.bin").write_bytes(b"Chroma wrote to its retrieval copy")

            self.assertEqual(record["copy_file_sha256_before_retrieval"], store_file_hashes(source))
            self.assertEqual(store_file_hashes(source), {
                "manifest.json": hashlib.sha256(b"{}").hexdigest(),
                "data_level0.bin": hashlib.sha256(b"approved-index").hexdigest(),
            })
            self.assertNotEqual(store_file_hashes(copy), store_file_hashes(source))


if __name__ == "__main__":
    unittest.main()
