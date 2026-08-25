# -*- coding: utf-8 -*-
"""finchat.kb — Arabic normalization + in-memory retrieval scoring + one-time seed import.
Few hundred entries — plain token-overlap scoring beats dragging in an FTS engine."""
import json
import re

from . import db as _db

# tashkeel/tatweel range — write with \u escapes, NOT literal combining chars
_TASHKEEL = re.compile(u"[ؐ-ًؚ-ٰۖ-ۭـ]")
# Arabic-range punctuation (؟ ، ؛ etc.) must be stripped explicitly first,
# since it falls inside the "keep Arabic letters" allowance below.
_ARABIC_PUNCT = re.compile(u"[؟،؛٪]")
_PUNCT = re.compile(r"[^\w\s؀-ۿ]")

# messy-typing normalizer: letters repeated 3+ times collapse (مصروووف → مصروف)
_REPEAT = re.compile(r"(.)\1{2,}")


def normalize_ar(s):
    s = str(s or "").strip().lower()
    s = _TASHKEEL.sub("", s)
    s = (s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
          .replace("ة", "ه").replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي"))
    s = _ARABIC_PUNCT.sub(" ", s)
    s = _PUNCT.sub(" ", s)
    s = _REPEAT.sub(r"\1", s)
    return re.sub(r"\s+", " ", s).strip()


_STOP = set(("في من الي على عن هل ما هو هي انا انت انتم كيف وش ليش ابغي ابي عندي فيه هذا هذه ذا "
             "the a an is are to of and or for how what why my i").split())


def _stem(t):
    """Strip the glued و/ال prefixes so «والتصدير» matches «تصدير»."""
    if t.startswith("وال") and len(t) > 4:
        return t[3:]
    if t.startswith("ال") and len(t) > 3:
        return t[2:]
    if t.startswith("و") and len(t) > 3:
        return t[1:]
    return t


def tokens(s):
    return [_stem(t) for t in normalize_ar(s).split() if t not in _STOP and len(t) > 1]


def _entry_tokens(e):
    if "_tokens" not in e:
        e["_tokens"] = set(tokens((e.get("q_ar") or "") + " " + (e.get("tags") or "")
                                  + " " + (e.get("answer_ar") or "")[:120]))
    return e["_tokens"]


def retrieve(question, entries, k=8):
    qt = tokens(question)
    if not qt:
        return []
    scored = []
    for e in entries:
        et = _entry_tokens(e)
        if not et:
            continue
        inter = sum(1 for t in qt if t in et)
        # partial-prefix credit: اعتمد matches اعتماد (root-ish, cheap)
        if inter == 0:
            inter = sum(0.5 for t in qt for w in et if len(t) > 3 and (w.startswith(t) or t.startswith(w)))
        if inter <= 0:
            continue
        scored.append((inter / (len(et) ** 0.5), e))
    scored.sort(key=lambda x: -x[0])
    return [e for _s, e in scored[:k]]


def seed_if_empty(path):
    """Import seed_kb.json on first boot ONLY. DB is the source of truth afterwards."""
    if _db.kb_count() > 0:
        return 0
    with open(path, encoding="utf-8") as f:
        items = json.load(f)
    n = 0
    for it in items:
        if not (it.get("q_ar") and it.get("answer_ar")):
            continue
        _db.kb_upsert(it["q_ar"], it["answer_ar"], links=it.get("links") or [],
                      tags=it.get("tags") or "", source="seed")
        n += 1
    return n
