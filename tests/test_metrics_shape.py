"""T2 — the counters. Without these there is no answer to "did v2 beat v1".

`cost_usd` and `tokens_used` had ZERO occurrences in bot.py before this work, so the
rollout gate "no >20% cost regression" had nothing behind it to measure.
"""

import unittest

import bot

REQUIRED = [
    "silent_total", "silent_by_reason",
    "guard_blocks", "guard_blocks_by_code",
    "collisions_avoided",
    "commitments_backed", "commitments_blocked",
    "incidents_harm", "incidents_habitability", "incidents_security",
    "unattributed_outbound",
    "memory_used", "memory_absent",
    "latency_ms", "cost_usd",
]


class DayRowShapeTest(unittest.TestCase):

    def test_every_required_counter_exists(self):
        row = bot._new_day_row()
        for key in REQUIRED:
            with self.subTest(key):
                self.assertIn(key, row)

    def test_the_pre_existing_counters_are_untouched(self):
        row = bot._new_day_row()
        for key in ("replies_total", "replies_auto", "escalations_created",
                    "drafts_made", "confidence_sum", "topics", "apartments_touched"):
            self.assertIn(key, row)

    def test_dict_counters_start_empty_and_scalars_start_at_zero(self):
        row = bot._new_day_row()
        self.assertEqual(row["silent_by_reason"], {})
        self.assertEqual(row["guard_blocks_by_code"], {})
        self.assertEqual(row["latency_ms"], [])
        self.assertEqual(row["silent_total"], 0)
        self.assertEqual(row["cost_usd"], 0.0)

    def test_a_fresh_row_is_not_shared_between_days(self):
        a, b = bot._new_day_row(), bot._new_day_row()
        a["silent_by_reason"]["x"] = 1
        self.assertEqual(b["silent_by_reason"], {}, "mutable defaults would fuse the days")


class MetricBumpTest(unittest.TestCase):

    def setUp(self):
        self.day = "2099-01-01"                      # a key nothing else touches
        bot._daily_metrics.pop(self.day, None)

    def tearDown(self):
        bot._daily_metrics.pop(self.day, None)

    def test_a_flat_key_still_works(self):
        bot.metric_bump("silent_total", day=self.day)
        bot.metric_bump("silent_total", day=self.day)
        self.assertEqual(bot._day_row(self.day)["silent_total"], 2)

    def test_a_dotted_key_lands_in_the_nested_dict(self):
        bot.metric_bump("silent_by_reason.human_active", day=self.day)
        bot.metric_bump("silent_by_reason.human_active", day=self.day)
        bot.metric_bump("silent_by_reason.own_echo", day=self.day)
        row = bot._day_row(self.day)
        self.assertEqual(row["silent_by_reason"], {"human_active": 2, "own_echo": 1})
        self.assertNotIn("silent_by_reason.human_active", row,
                         "a dotted key must not become a flat string key")

    def test_guard_block_codes_are_counted_per_rule(self):
        bot.metric_bump("guard_blocks_by_code.ACCESS_CODE", day=self.day)
        bot.metric_bump("guard_blocks_by_code.MONEY", day=self.day)
        self.assertEqual(bot._day_row(self.day)["guard_blocks_by_code"],
                         {"ACCESS_CODE": 1, "MONEY": 1})

    def test_bumping_never_raises(self):
        bot.metric_bump("a.b.c", day=self.day)       # extra dots are not a crash
        bot.metric_bump("", day=self.day)


class CostAndLatencyTest(unittest.TestCase):

    def setUp(self):
        self.day = "2099-01-02"
        bot._daily_metrics.pop(self.day, None)

    def tearDown(self):
        bot._daily_metrics.pop(self.day, None)

    def test_latency_samples_are_kept_raw(self):
        # A p95 cannot be recovered from a running average.
        for ms in (100, 250, 900):
            bot.metric_record_latency(ms, day=self.day)
        self.assertEqual(bot._day_row(self.day)["latency_ms"], [100, 250, 900])

    def test_latency_is_capped_so_a_busy_day_cannot_grow_forever(self):
        for _ in range(5200):
            bot.metric_record_latency(10, day=self.day)
        self.assertLessEqual(len(bot._day_row(self.day)["latency_ms"]), 5000)

    def test_tokens_and_cost_accumulate(self):
        bot.metric_record_cost(1_000_000, 1_000_000, day=self.day)
        row = bot._day_row(self.day)
        self.assertEqual(row["tokens_in"], 1_000_000)
        self.assertEqual(row["tokens_out"], 1_000_000)
        self.assertAlmostEqual(
            row["cost_usd"],
            bot.ASSISTANT_COST_IN_PER_MTOK + bot.ASSISTANT_COST_OUT_PER_MTOK, places=4)

    def test_missing_usage_is_not_a_crash(self):
        bot.metric_record_cost(None, None, day=self.day)
        self.assertEqual(bot._day_row(self.day)["cost_usd"], 0.0)


class InstrumentationTest(unittest.TestCase):

    def test_claude_draft_records_latency_and_cost(self):
        import inspect
        src = inspect.getsource(bot.claude_draft)
        self.assertIn("metric_record_latency", src)
        self.assertIn("metric_record_cost", src)
        self.assertIn("usage", src)


if __name__ == "__main__":
    unittest.main()
