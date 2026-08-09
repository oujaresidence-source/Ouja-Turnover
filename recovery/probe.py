# -*- coding: utf-8 -*-
"""
recovery.probe — §16 step 3's cost measurement. Run this, read the number, THEN decide.

    python3 -m recovery.probe --source hostaway --limit 10          # compaction only, free
    python3 -m recovery.probe --source hostaway --limit 10 --live   # + real extraction calls
    python3 -m recovery.probe --source sample                       # offline, no credentials

Deliberately NOT imported by recovery/__init__.py. The hostaway source imports bot.py, and
bot.py is a 3.8MB module that builds a Discord client at import time — that belongs in a
script you run on purpose, never in the package the running bot loads.

WHAT --live COSTS: at most one Haiku call per reservation (a second and a third only if the
model returns invalid JSON twice). The printed SAR total is the real bill, computed from the
usage block the API returns, not an estimate.

WITHOUT --live it makes ZERO API calls and prints measured character counts plus a token
BAND. The band is an estimate and is labelled as one — Arabic tokenizes at roughly 2–3
characters per token depending on script and diacritics, so the band brackets the truth
instead of pretending to a precision it does not have. Use --live for the real figure.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from recovery import engine, llm  # noqa: E402

# Arabic characters-per-token band. Only used for the free estimate.
CHARS_PER_TOKEN_LO = 2.0     # pessimistic -> more tokens -> higher cost
CHARS_PER_TOKEN_HI = 3.0
PROMPT_OVERHEAD_CHARS = len(llm.PROMPT)   # the schema block rides on every call


# ---------------------------------------------------------------- sources

def source_sample():
    """Offline corpus. The COMPLAINT LINES are real guest Arabic lifted from the project's
    own eval set (golden_set.seed.jsonl); the multi-turn STAY SHAPE around them is
    constructed, because that eval set stores one message per case and this project has no
    stored multi-turn conversations. Treat the resulting numbers as indicative of shape,
    not as a measurement of live traffic — that is what --source hostaway is for."""
    complaints = []
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "golden_set.seed.jsonl")
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                row = json.loads(line)
                txt = (row.get("guest_text") or "").strip()
                if txt and engine.has_complaint(txt):
                    complaints.append((row.get("id"), txt))
    except Exception as e:
        print("sample source error:", e)
    if not complaints:
        complaints = [("fallback", "المكيف ما يشتغل ومحد رد علي")]

    # Message lengths here are sized to a real Hostaway thread: guest turns run 30–140
    # characters, staff replies 40–180, and the arrival templates 150–400 — the templates
    # are most of a thread's bulk, which is exactly what compaction is aimed at.
    filler_guest = [
        "طيب وش الوضع الحين؟ صار لنا فترة ننتظر وما وصلنا أي رد منكم",
        "لين متى بالضبط؟ أنا معي عيال صغار والوضع صعب علينا بصراحة",
        "ياليت تردون علي بسرعة لأني محتاج أعرف وش أسوي",
        "الحين صار لي ساعتين أنتظر ومحد كلمني ولا طمنّي على شي",
        "ممكن أحد يتواصل معي على الجوال بدل الرسائل؟ أسرع لي",
        "أنا ما أبي أزعجكم بس هذي ثالث مرة أكتب لكم بنفس الموضوع",
    ]
    filler_staff = [
        "نعتذر منك جداً على التأخير، فريقنا يتابع الموضوع الحين ونرجع لك بأقرب وقت",
        "وصلنا طلبك وسجلناه، أعطنا مهلة بسيطة ونحدثك أول بأول",
        "الفني بالطريق لك الحين، يوصل خلال ثلاثين دقيقة بإذن الله",
        "شكراً لسعة صدرك، رفعنا الموضوع للمشرف المباشر عشان يتابعه شخصياً",
    ]
    templates = [
        "أهلاً وسهلاً فيك في عوجا 🌿\nرمز الدخول: 4417\nدليل الوصول الكامل: "
        "https://oujaguide.example/turaif\nموعد الدخول من الساعة 3 العصر، وموعد الخروج "
        "الساعة 12 ظهراً. الدخول ذاتي بالكامل، ما تحتاج تقابل أحد.",
        "كلمة المرور للواي فاي: OUJA2026\nاسم الشبكة: Ouja_Guest\nإذا واجهتك أي مشكلة "
        "في الاتصال، أعد تشغيل الراوتر الموجود بجانب التلفزيون.",
        "Welcome! We are truly delighted by your booking with Ouja Residence. "
        "We've prepared everything for your arrival: self check-in, fresh linens, and "
        "a full arrival guide at the link above. Check-out time is 12:00 noon.",
        "تذكير بموعد الخروج الساعة 12 ظهراً. نتمنى لك إقامة سعيدة، وإذا احتجت أي شي "
        "لا تتردد تكتب لنا هنا.",
    ]

    stays = []
    for n, (cid, complaint) in enumerate(complaints[:12]):
        msgs = [{"who": "guest", "text": "مساء الخير، وصلنا الشقة الحين"},
                {"who": "staff", "text": templates[0]},
                {"who": "staff", "text": templates[1]},
                {"who": "guest", "text": "تمام"},
                {"who": "guest", "text": "شكرا"}]
        for i in range(14):                      # the long middle a real stay accumulates
            msgs.append({"who": "guest", "text": filler_guest[i % len(filler_guest)]})
            msgs.append({"who": "staff", "text": filler_staff[i % len(filler_staff)]})
            if i % 5 == 4:
                msgs.append({"who": "staff", "text": templates[(i // 5) % len(templates)]})
        msgs.append({"who": "guest", "text": complaint})
        msgs.append({"who": "staff",
                     "text": "نعتذر بشدة عن اللي صار، نرسل لك الفني خلال ساعة ونتابع معك"})
        msgs.append({"who": "guest",
                     "text": "لين الحين ما جا أحد وهذي مو أول مرة يصير فيها نفس الشي"})
        msgs.append({"who": "guest", "text": "👍"})
        stays.append({"reservation_id": "SAMPLE-%s-%d" % (cid, n), "messages": msgs})
    return stays


def source_hostaway(limit):
    """Real conversations for the current in-house guests. READ-ONLY."""
    import bot                                    # heavy, on purpose, and only here
    from datetime import datetime

    today = datetime.now(bot.TZ).date()
    res = bot.fetch_inhouse(today) or []
    listings = bot.get_listings_map() or {}
    out, seen = [], set()
    for r in res:
        if len(out) >= limit:
            break
        rid = r.get("id")
        if not rid or rid in seen:
            continue
        seen.add(rid)
        cid = bot._guest_conversation_id(rid, r.get("conversationId"))
        if not cid:
            continue
        raw = bot._guest_msgs(cid) or []
        stay = bot._guest_messages_since(raw, str(r.get("arrivalDate") or "")[:10])
        msgs = [{"who": "guest" if bot._msg_is_inbound(m) else "staff",
                 "text": (m.get("body") or "").strip(),
                 "ts": bot._msg_time(m)}
                for m in stay if (m.get("body") or "").strip()]
        if not msgs:
            continue
        out.append({"reservation_id": str(rid),
                    "unit": listings.get(r.get("listingMapId")) or "",
                    "guest": r.get("guestName") or "",
                    "messages": msgs})
    return out


# ---------------------------------------------------------------- the live call

def make_live_call():
    """Reuses bot.py's transport (same endpoint, same retry policy, same key) but reads the
    usage block that bot.claude_text discards."""
    import bot
    import requests

    def call(model, prompt, max_tokens, temperature):
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": bot.ANTHROPIC_API_KEY,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": model, "max_tokens": max_tokens, "temperature": temperature,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=60)
        r.raise_for_status()
        data = r.json()
        text = "".join(b.get("text", "") for b in (data.get("content") or [])
                       if b.get("type") == "text")
        usage = data.get("usage") or {}
        return {"text": text,
                "input_tokens": usage.get("input_tokens") or 0,
                "output_tokens": usage.get("output_tokens") or 0}

    return call


# ---------------------------------------------------------------- report

def raw_chars(msgs):
    return sum(len(m.get("text") or "") for m in msgs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=("sample", "hostaway"), default="sample")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--live", action="store_true",
                    help="make REAL API calls and report the measured bill")
    args = ap.parse_args()

    stays = (source_hostaway(args.limit) if args.source == "hostaway"
             else source_sample())[:args.limit]
    if not stays:
        print("no conversations found for source=%s" % args.source)
        return 1

    call = make_live_call() if args.live else None
    rows, tot_raw, tot_comp, tot_in, tot_out, tot_sar, tot_calls = [], 0, 0, 0, 0, 0.0, 0

    for st in stays:
        msgs = st["messages"]
        rc = raw_chars(msgs)
        comp = engine.compact(msgs)
        cc = len(comp)
        tot_raw += rc
        tot_comp += cc
        row = {"id": st["reservation_id"], "msgs": len(msgs), "raw": rc, "comp": cc,
               "cut": (100.0 * (rc - cc) / rc) if rc else 0.0,
               "hash": engine.content_hash(comp)[:10]}
        if call:
            clean, meta = llm.extract(comp, call)
            row.update(calls=meta["calls"], itok=meta["input_tokens"],
                       otok=meta["output_tokens"], sar=meta["cost_sar"],
                       ok=clean is not None, esc=meta["escalated"])
            tot_in += meta["input_tokens"]
            tot_out += meta["output_tokens"]
            tot_sar += meta["cost_sar"]
            tot_calls += meta["calls"]
        rows.append(row)

    n = len(rows)
    print("\n=== recovery cost probe · source=%s · n=%d · live=%s ===\n"
          % (args.source, n, bool(args.live)))
    hdr = "%-26s %5s %8s %8s %7s" % ("reservation", "msgs", "raw ch", "sent ch", "cut%")
    if call:
        hdr += " %5s %7s %7s %8s" % ("calls", "in tok", "out tok", "SAR")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        line = "%-26s %5d %8d %8d %6.1f%%" % (r["id"][:26], r["msgs"], r["raw"],
                                              r["comp"], r["cut"])
        if call:
            line += " %5d %7d %7d %8.4f%s" % (r["calls"], r["itok"], r["otok"], r["sar"],
                                              " ⚠esc" if r.get("esc") else "")
        print(line)

    print("-" * len(hdr))
    print("totals: raw %d ch -> sent %d ch (%.1f%% cut), avg sent %d ch/ticket"
          % (tot_raw, tot_comp, (100.0 * (tot_raw - tot_comp) / tot_raw) if tot_raw else 0,
             tot_comp / n))
    over = sum(1 for r in rows if r["comp"] >= 6000)
    print("hit the 6,000-char cap: %d of %d" % (over, n))

    if call:
        print("\nMEASURED: %d API calls, %d input + %d output tokens, %.4f SAR total"
              % (tot_calls, tot_in, tot_out, tot_sar))
        print("per ticket: %.4f SAR   ·   at 15 tickets/day: %.2f SAR/day, %.2f SAR/month"
              % (tot_sar / n, tot_sar / n * 15, tot_sar / n * 15 * 30))
        print("(cache: a re-run on unchanged conversations costs 0.0000 SAR)")
    else:
        # Free estimate, explicitly a band.
        avg_in_chars = (tot_comp / n) + PROMPT_OVERHEAD_CHARS
        lo_in, hi_in = avg_in_chars / CHARS_PER_TOKEN_HI, avg_in_chars / CHARS_PER_TOKEN_LO
        lo_out, hi_out = 250, 450          # the schema's own answer, 700 max_tokens
        lo = llm.cost_sar(llm.MODEL_PRIMARY, lo_in, lo_out)
        hi = llm.cost_sar(llm.MODEL_PRIMARY, hi_in, hi_out)
        print("\nESTIMATE ONLY (no API calls made — run with --live for the real number)")
        print("  input  ~%d-%d tokens/ticket   output ~%d-%d tokens"
              % (lo_in, hi_in, lo_out, hi_out))
        print("  cost   ~%.4f-%.4f SAR/ticket on %s" % (lo, hi, llm.MODEL_PRIMARY))
        print("  at 15 tickets/day: ~%.2f-%.2f SAR/day, ~%.2f-%.2f SAR/month"
              % (lo * 15, hi * 15, lo * 15 * 30, hi * 15 * 30))
    print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
