# -*- coding: utf-8 -*-
"""finchat — «مساعد المركز المالي». KB-grounded Arabic chatbot for the accounting team.
bot.py calls finchat.wire({...}) then finchat.register_routes(app). All knowledge lives in
brain.db (finchat_* tables) — updated at runtime, never via redeploy."""
import os

from . import db, kb, answer, erpmap, routes  # noqa: F401

__all__ = ["wire", "register_routes"]

SEED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_kb.json")


def wire(caps):
    routes.HOST.update(caps)
    answer.CFG.update({
        "claude": caps["claude"],
        "conf": float(os.environ.get("FINCHAT_CONF", "0.6")),
        "model_fast": os.environ.get("FINCHAT_MODEL_FAST", "claude-haiku-4-5-20251001"),
        "model_smart": os.environ.get("FINCHAT_MODEL_SMART", "claude-sonnet-5"),
        "daily_cap": int(os.environ.get("FINCHAT_DAILY_CAP", "80")),
        "enabled": True,
    })
    try:
        n = kb.seed_if_empty(SEED_PATH)
        print("[finchat] ready: kb=%d (seeded=%d)" % (db.kb_count(), n))
    except Exception as e:
        print("[finchat] seed skipped:", e)


def register_routes(app):
    routes.register(app)
