import unittest

from qwen_api_client import ChatSettings, request_payload


class QwenTemplateOptionTests(unittest.TestCase):
    def test_standard_payload_does_not_add_template_options(self):
        payload = request_payload([{"role": "user", "content": "ping"}], ChatSettings())
        self.assertNotIn("chat_template_kwargs", payload)

    def test_explicit_qwen_vllm_probe_adds_only_disable_thinking_option(self):
        settings = ChatSettings(chat_template_kwargs={"enable_thinking": False})
        payload = request_payload([{"role": "user", "content": "ping"}], settings)
        self.assertEqual(payload["chat_template_kwargs"], {"enable_thinking": False})

    def test_other_undocumented_template_options_are_rejected(self):
        for value in ({"enable_thinking": True}, {"top_k": 1}, {"enable_thinking": False, "x": 1}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ChatSettings(chat_template_kwargs=value)


if __name__ == "__main__":
    unittest.main()
