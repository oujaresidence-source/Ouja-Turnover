# -*- coding: utf-8 -*-
"""
recovery.llm — the ONE extraction call, and the only place in this project that
measures what a Claude call actually cost.

WHY THIS DOESN'T USE bot.claude_json
    Every other feature calls bot.py's `claude_json`, which returns the parsed text and
    throws the usage block away. §3.4 requires this feature to log input_tokens,
    output_tokens and model per ticket and to report a monthly bill in SAR — so it reads
    the raw response instead. That is the only reason for the duplication; the transport
    (requests + the same retry policy) is bot.py's, injected through HOST, so there is
    still exactly one HTTP client and one API key in the process.

    Anthropic publishes an official Python SDK. This project has never used it — bot.py
    posts to /v1/messages with `requests` — and adding a dependency to requirements.txt
    redeploys the live bot for a cosmetic gain. Matching the surrounding code is the
    smaller risk; revisit only if the SDK is adopted project-wide.
"""

import json
import re

from . import engine

MODEL_PRIMARY = "claude-haiku-4-5"      # §3.3 — extraction is a cheap task
MODEL_ESCALATION = "claude-sonnet-5"    # §3.3 — only after JSON validation fails twice
MAX_TOKENS = 700
TEMPERATURE = 0

USD_TO_SAR = 3.75                       # the riyal's peg — fixed, not a live rate

# USD per MILLION tokens, from the Anthropic pricing table (checked 2026-08-06).
#
# TRAP WITH A DATE ON IT: claude-sonnet-5 is inside an introductory window ($2/$10)
# that ENDS 2026-08-31. From 2026-09-01 it is $3/$15 — a 50% jump on the escalation
# path. The table carries both so the monthly report cannot quietly under-report the
# bill the day the intro expires.
PRICING = {
    "claude-haiku-4-5":  {"in": 1.00, "out": 5.00},
    "claude-sonnet-5":   {"in": 2.00, "out": 10.00,      # introductory
                          "after": {"date": "2026-09-01", "in": 3.00, "out": 15.00}},
}


def price_for(model, on_date=None):
    """USD per million tokens for `model`, honouring a dated price change."""
    row = PRICING.get(model)
    if not row:
        return None
    after = row.get("after")
    if after and on_date and str(on_date)[:10] >= after["date"]:
        return {"in": after["in"], "out": after["out"]}
    return {"in": row["in"], "out": row["out"]}


def cost_sar(model, input_tokens, output_tokens, on_date=None):
    """SAR for one call. Returns 0.0 for an unknown model rather than guessing — a
    made-up number in a financial report is worse than a visible zero."""
    p = price_for(model, on_date)
    if not p:
        return 0.0
    usd = (float(input_tokens or 0) / 1e6) * p["in"] + (float(output_tokens or 0) / 1e6) * p["out"]
    return round(usd * USD_TO_SAR, 4)


# ---------------------------------------------------------------------------
# §3.5 — the extraction prompt, verbatim. Do not "improve" the wording without
# re-running the cost probe: every edit invalidates the whole analysis cache
# (the hash covers the conversation, not the prompt), so a reword silently
# re-bills every open reservation.
# ---------------------------------------------------------------------------
PROMPT = """You extract a guest complaint summary. Output ONLY valid JSON, no other text.
Schema:
{
  "headline_ar": "one sentence, max 12 words, Najdi Arabic, what went wrong",
  "timeline": [{"when":"...","what_ar":"max 15 words"}],   // 3-5 items, chronological
  "quotes": ["guest's own words, max 12 words each"],       // max 2, verbatim from guest
  "root_cause": "maintenance|cleanliness|checkin|noise|amenity|staff|pricing|expectation|other",
  "physical_issue": true|false,
  "already_promised_ar": "what staff already promised, or null",
  "unresolved_ar": "what is still open, max 20 words",
  "severity": 1-5,
  "call_opener_ar": "one Najdi sentence the agent says after greeting, references the specific issue"
}
Conversation:
<<<CONVERSATION>>>"""

RETRY_SUFFIX = "\n\nYour previous output was invalid JSON. Output only the JSON object."


def build_prompt(compacted):
    return PROMPT.replace("<<<CONVERSATION>>>", compacted or "")


def _parse(text):
    """Same forgiveness as bot.claude_json: strip fences, else first {...} block."""
    if not text:
        return None
    t = str(text).replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(t)
    except Exception:
        m = re.search(r"\{.*\}", t, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


def extract(compacted, call, on_date=None):
    """Run the extraction. `call(model, prompt, max_tokens, temperature)` must return
    {"text": str, "input_tokens": int, "output_tokens": int} — injected so this module
    stays testable without a network or an API key.

    §3.3's ladder: primary model, one retry with the corrective suffix, then ONE
    escalation to Sonnet. Returns (clean|None, meta). `meta` always carries every
    attempt's usage, so a ticket that cost three calls reports three calls.
    """
    attempts = []

    def _try(model, prompt):
        r = call(model=model, prompt=prompt, max_tokens=MAX_TOKENS,
                 temperature=TEMPERATURE) or {}
        rec = {"model": model,
               "input_tokens": int(r.get("input_tokens") or 0),
               "output_tokens": int(r.get("output_tokens") or 0)}
        rec["cost_sar"] = cost_sar(model, rec["input_tokens"], rec["output_tokens"], on_date)
        attempts.append(rec)
        clean, err = engine.validate_extraction(_parse(r.get("text")))
        rec["ok"] = clean is not None
        rec["error"] = err
        return clean, err

    base = build_prompt(compacted)

    clean, err = _try(MODEL_PRIMARY, base)
    if clean is None:
        clean, err = _try(MODEL_PRIMARY, base + RETRY_SUFFIX)
    if clean is None:
        # §3.3: escalate ONLY after two validation failures, and log it.
        clean, err = _try(MODEL_ESCALATION, base + RETRY_SUFFIX)

    meta = {
        "attempts": attempts,
        "calls": len(attempts),
        "model": attempts[-1]["model"] if attempts else None,
        "input_tokens": sum(a["input_tokens"] for a in attempts),
        "output_tokens": sum(a["output_tokens"] for a in attempts),
        "cost_sar": round(sum(a["cost_sar"] for a in attempts), 4),
        "escalated": any(a["model"] == MODEL_ESCALATION for a in attempts),
        "error": None if clean else (err or "extraction failed"),
    }
    return clean, meta
