# -*- coding: utf-8 -*-
"""
business.manual — the "what Hostaway can't know" layer.

Social reach, followers, units under management, compounds, districts, licences:
facts no PMS can produce, that Faisal confirms by hand. The hard rule (superprompt
§3): every entry needs value, as_of, source. No as_of, no render — fail loud in
dev, silent in prod, so a stale or unsourced brag never reaches a diligence reader.

Stored as JSON (not YAML) to avoid a new runtime dependency and to match every other
hand-editable store in this repo (listings_store.json, dispatch_state.json, ...).
The strict value/as_of/source gate is the part the brief actually cares about.
"""
import json
import os

REQUIRED_FIELDS = ("value", "as_of", "source")


class ManualMetricError(ValueError):
    """Raised in strict mode when a manual entry is missing a required field."""


def _missing_fields(entry):
    if not isinstance(entry, dict):
        return list(REQUIRED_FIELDS)
    missing = []
    for f in REQUIRED_FIELDS:
        v = entry.get(f)
        if v is None or (isinstance(v, str) and not v.strip()):
            missing.append(f)
    return missing


def _default_strict():
    """Dev = strict (fail loud); prod = lenient (drop silently).

    Railway sets RAILWAY_ENVIRONMENT; its presence marks production.
    """
    return not os.environ.get("RAILWAY_ENVIRONMENT")


def load_manual_metrics(data=None, path=None, strict=None):
    """Return only the manual entries that carry value + as_of + source.

    data:   an already-parsed dict (key -> entry). Takes precedence over path.
    path:   a JSON file to read when data is None.
    strict: True -> raise ManualMetricError on the first invalid entry.
            False -> drop invalid entries silently.
            None -> dev strict, prod lenient (_default_strict).
    """
    if strict is None:
        strict = _default_strict()
    if data is None:
        if not path or not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)

    valid = {}
    for key, entry in (data or {}).items():
        missing = _missing_fields(entry)
        if missing:
            if strict:
                raise ManualMetricError(
                    "manual metric %r is missing required field(s): %s"
                    % (key, ", ".join(missing))
                )
            continue
        valid[key] = entry
    return valid
