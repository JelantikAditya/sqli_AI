import unittest

from qwen_api_generation_feedback_summary_smoke import compact_feedback


def observation(markers):
    return {"http_status": 200, "content_markers": markers}


class CompactFeedbackTests(unittest.TestCase):
    def test_boolean_feedback_summarizes_paired_markers_and_status(self):
        trials = [{"true_condition": observation(["user_id_exists"]),
                   "false_condition": observation(["user_id_exists"])}
                  for _ in range(3)]
        result = compact_feedback("S2", {"previous_observations": trials})
        self.assertTrue(result["true_false_content_markers_equal_all_trials"])
        self.assertEqual(result["shared_content_markers"], ["user_id_exists"])
        self.assertEqual(result["http_statuses"], [200])

    def test_time_feedback_retains_all_measured_pair_deltas(self):
        deltas = [-10.52, 0.1, -3.18]
        trials = [{"single": observation(["user_id_exists"]),
                   "no_delay_control": observation(["user_id_exists"]),
                   "delta_ms": delta} for delta in deltas]
        result = compact_feedback("S3", {"previous_observations": trials})
        self.assertTrue(result["single_control_content_markers_equal_all_trials"])
        self.assertEqual(result["shared_content_markers"], ["user_id_exists"])
        self.assertEqual(result["timing_delta_ms"], deltas)


if __name__ == "__main__":
    unittest.main()
