# -*- coding: utf-8 -*-
"""
ASSUMPTIONS STORE  (spec §3)

Operator answers persist per-unit and PRE-FILL next time — but every one must be
explicitly RE-CONFIRMED each run. Pre-filled != confirmed. This store holds the last
saved values; `prefill()` returns them with every field marked ``confirmed=False`` so
the wizard shows the stored value and requires a tap to confirm or edit. Nothing this
store returns is ever treated as confirmed on its own — confirmation happens per run.

Storage is dependency-injected (``load``/``save`` callables, matching the bot's
state_path/load_json/save_json caps) so the module is unit-testable without disk.
"""
from __future__ import annotations

import copy

_STORE_NAME = "owner_report_assumptions.json"


class AssumptionStore:
    def __init__(self, load, save, store_name: str = _STORE_NAME):
        """load(name, default) -> obj ; save(name, obj) -> None."""
        self._load = load
        self._save = save
        self._name = store_name

    def _all(self) -> dict:
        return self._load(self._name, {}) or {}

    def stored(self, lid) -> dict:
        """Raw last-saved answers for a unit (values only), or {} if none."""
        return copy.deepcopy(self._all().get(str(lid), {}).get("values", {}))

    def prefill(self, lid) -> dict:
        """Return every stored field wrapped as {value, confirmed: False, stored_at}.

        Pre-filled is NOT confirmed. The caller must collect an explicit confirmation
        for each field this run before it counts.
        """
        rec = self._all().get(str(lid), {})
        vals = rec.get("values", {})
        stamp = rec.get("saved_at")
        return {
            field: {"value": v, "confirmed": False, "stored_at": stamp}
            for field, v in vals.items()
        }

    def record(self, lid, values: dict, actor: str, now_iso: str) -> None:
        """Persist the values confirmed/edited this run as the new prefill baseline."""
        allv = self._all()
        allv[str(lid)] = {"values": copy.deepcopy(values), "saved_at": now_iso, "saved_by": actor}
        self._save(self._name, allv)

    @staticmethod
    def all_confirmed(run_answers: dict) -> bool:
        """True iff every field in this run carries an explicit confirmed=True.

        ``run_answers`` shape: {field: {value, confirmed: bool}}. An empty run is not
        'all confirmed' — there is nothing to render from.
        """
        if not run_answers:
            return False
        return all(bool(a.get("confirmed")) for a in run_answers.values())

    @staticmethod
    def unconfirmed_fields(run_answers: dict) -> list:
        return sorted(f for f, a in run_answers.items() if not a.get("confirmed"))

    @staticmethod
    def values_of(run_answers: dict) -> dict:
        """Flatten a confirmed run back to plain {field: value}."""
        return {f: a.get("value") for f, a in run_answers.items()}
