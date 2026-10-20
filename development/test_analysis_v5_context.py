"""Fail-closed checks for truncated prompts and unsupported template branches."""

import copy
import unittest

import preflight_analysis_v5_context as context


class ContextChecks(unittest.TestCase):
    def setUp(self):
        self.options={"num_ctx":4096,"num_predict":768}
        self.response={"done":True,"done_reason":"stop","prompt_eval_count":1684,"eval_count":1}

    def test_reserved_allowance_uses_configured_output_limit(self):
        self.assertEqual(context.runtime_check(self.response,1684,self.options)["reserved_headroom"],1644)

    def test_shorter_runtime_prompt_cannot_pass_as_untruncated(self):
        response=copy.deepcopy(self.response);response["prompt_eval_count"]=1683
        with self.assertRaisesRegex(ValueError,"complete offline"):
            context.runtime_check(response,1684,self.options)

    def test_short_observed_output_does_not_bypass_context_reservation(self):
        with self.assertRaisesRegex(ValueError,"configured output allowance"):
            context.runtime_check(self.response,1684,{"num_ctx":2000,"num_predict":768})

    def test_limit_stop_and_missing_accounting_are_rejected(self):
        for change in ({"done_reason":"length"},{"eval_count":768},{"eval_count":None}):
            with self.assertRaises(ValueError):context.runtime_check({**self.response,**change},1684,self.options)

    def test_uninspected_chat_template_branch_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"two-message"):
            context.serialized_chat({"messages":[{"role":"user","content":"x"}]})
        with self.assertRaises(ValueError):
            context.serialized_chat({"messages":[{"role":"system","content":"x"},{"role":"user","content":"y"}],"tools":[{}]})


if __name__=="__main__":
    unittest.main()
