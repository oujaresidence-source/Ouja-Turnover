# -*- coding: utf-8 -*-
"""
«طلبات سام» offline replay — six real RR rooms (redacted) run through rrdesk with a fake clock,
compared line by line with the committed timeline (<room>.expected.txt).

A diff here means behaviour changed. If the change is intended, regenerate the snapshot:
    python3 -m rrdesk.replay tests/fixtures/rrdesk/rooms_replay/<room>.json > <room>.expected.txt
and say why in the commit. Run: python3 -m unittest tests.test_rrdesk_replay
"""

import glob
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from rrdesk import replay   # noqa: E402

ROOMS = sorted(glob.glob(os.path.join(ROOT, "tests", "fixtures", "rrdesk", "rooms_replay", "*.json")))


class Replay(unittest.TestCase):
    def test_there_are_five_to_eight_rooms(self):
        self.assertTrue(5 <= len(ROOMS) <= 8, len(ROOMS))

    def test_every_room_matches_its_snapshot(self):
        for fn in ROOMS:
            with self.subTest(room=os.path.basename(fn)):
                with open(fn, encoding="utf-8") as f:
                    room = json.load(f)
                with open(fn[:-5] + ".expected.txt", encoding="utf-8") as f:
                    want = f.read().rstrip(chr(10)).split(chr(10))
                got = chr(10).join(replay.replay(room)).rstrip(chr(10)).split(chr(10))
                self.assertEqual(got, want)

    def test_replay_is_deterministic(self):
        with open(ROOMS[0], encoding="utf-8") as f:
            room = json.load(f)
        self.assertEqual(replay.replay(room), replay.replay(room))


if __name__ == "__main__":
    unittest.main()
