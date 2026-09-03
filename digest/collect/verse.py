# -*- coding: utf-8 -*-
"""«آية الأسبوع» — the text comes ONLY from the Quran API (alquran.cloud, simple
script), never typed by us; the verse KEY is picked from a curated list in riyadh.json
(short, widely known, uplifting), rotating by issue number. If the API is down the
section is absent — a wrong letter in a verse is worse than no verse."""

import json

from ..dates import ar_digits

SOURCE = "القرآن الكريم"
API = "https://api.alquran.cloud/v1/ayah/%s/quran-simple"   # simple script: our faces render it cleanly


def pick_key(keys, issue_no):
    keys = [k for k in (keys or []) if k]
    if not keys:
        return ""
    return keys[(int(issue_no) - 1) % len(keys)]


def _split(key):
    """'94:5-6' -> ['94:5', '94:6']; '65:2' -> ['65:2']."""
    surah, _, ayahs = key.partition(":")
    if "-" in ayahs:
        a, b = ayahs.split("-", 1)
        return ["%s:%d" % (surah, n) for n in range(int(a), int(b) + 1)]
    return [key]


def parse(payloads):
    """payloads = [(url, json_text)] in ayah order -> {text, surah_ar, ayahs, ref_ar, source} or None."""
    texts, surah, nums = [], "", []
    for url, txt in payloads:
        try:
            d = json.loads(txt or "")
            data = d.get("data") or {}
            if d.get("code") != 200 or not data.get("text"):
                return None
        except Exception:
            return None
        texts.append(data["text"].strip())
        surah = surah or (data.get("surah") or {}).get("name", "")
        nums.append(int(data.get("numberInSurah") or 0))
    if not texts or not surah:
        return None
    ref = "%s · %s" % (surah, ar_digits(nums[0]) if len(nums) == 1 else "%s–%s" % (ar_digits(nums[0]), ar_digits(nums[-1])))
    return {"text": " ".join(texts), "surah_ar": surah, "ayahs": nums, "ref_ar": ref,
            "source": {"name": SOURCE, "url": payloads[0][0], "fetched_at": ""}}


def fetch(key, http, now):
    """-> verse dict or None. Every ayah of the key is fetched from the API."""
    if not key:
        return None
    payloads = []
    for k in _split(key):
        url = API % k
        try:
            status, final, ctype, txt = http.get_text(url)
        except Exception:
            return None
        if status != 200:
            return None
        payloads.append((final or url, txt))
    v = parse(payloads)
    if v:
        v["key"] = key
        v["source"]["fetched_at"] = now.isoformat(timespec="seconds")
    return v
