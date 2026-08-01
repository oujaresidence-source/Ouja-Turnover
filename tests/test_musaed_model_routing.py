"""Dedicated Sonnet 5 payloads for guest-facing and guest-analysis calls."""

import unittest
from unittest import mock

import bot


class _Response:
    status_code = 200
    headers = {}

    def __init__(self, text):
        self._text = text

    def raise_for_status(self):
        return None

    def json(self):
        return {"content": [{"type": "text", "text": self._text}]}


class TestMusaedModelRouting(unittest.TestCase):
    def test_guest_draft_uses_sonnet_five_without_adaptive_thinking(self):
        response = _Response(
            '{"action":"reply","reply":"Hello","intent":"other",'
            '"sentiment":"ok","confidence":0.9,"reason":""}'
        )
        with mock.patch.object(bot, "ANTHROPIC_API_KEY", "test"), \
             mock.patch.object(bot.requests, "post", return_value=response) as post:
            got = bot.claude_draft("Guest", "Unit", "Guest: Hello")
        self.assertEqual(got["reply"], "Hello")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "claude-sonnet-5")
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertGreaterEqual(payload["max_tokens"], 1000)

    def test_guest_analysis_sonnet_five_payload_has_safe_token_floor(self):
        with mock.patch.object(bot, "ANTHROPIC_API_KEY", "test"), \
             mock.patch.object(bot.requests, "post", return_value=_Response("ok")) as post:
            bot.claude_text("system", "user", max_tokens=300,
                            model="claude-sonnet-5")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(payload["max_tokens"], 1000)


if __name__ == "__main__":
    unittest.main()
