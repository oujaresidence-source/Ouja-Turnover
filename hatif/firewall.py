# -*- coding: utf-8 -*-
"""
hatif.firewall — PURE last check on every reply the WhatsApp reader composes. Rules as CODE,
not prompt prose (the «مساعد» v3 lesson). A reply with any violation is never sent; in silent
mode it is shown on Discord with the reason.

    COUNT      states how many apartments we have (owner rule 2026-11-13)
    BOOKED     claims a booking is made/confirmed (the bot cannot book; Airbnb finishes it)
    READY      says a unit is clean/ready (owner rule: never answer readiness)
    PRICE      a riyal figure that did not come from the bank or the live search
    PLACEHOLD  an unfilled template slot or a "None"/"undefined" leak
"""
import re

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

_COUNT = re.compile(
    r"(\d+)\s*(?:شقق|شقة|شقه|وحدة|وحدات|وحده)"
    r"|(?:عندنا|لدينا|فيه)\s+\d+\s"
    r"|\b\d+\s*(?:apartments|units)\b", re.I)
_BOOKED = re.compile(r"تم\s*(?:ال)?حجز|حجزنا\s*لك|حجزك\s*(?:تأكد|مؤكد|تم)|تأكد\s*حجزك|booking\s+(?:is\s+)?confirmed|we\s+booked", re.I)
_READY = re.compile(r"(?:الشقة|الشقه|شقتك|الوحدة)[^.\n؟!]{0,30}(?:جاهزة|جاهزه|نظيفة|نظيفه|تنظفت|انتظفت)")
_MONEY = re.compile(r"(\d[\d,]*)\s*(?:ر\.س|ريال|SAR|﷼)")
_PLACEHOLD = re.compile(r"\{\{|\}\}|\[[^\]]{0,20}\]|\bNone\b|\bundefined\b|\bNaN\b")


def _num(s):
    try:
        return int(str(s).replace(",", ""))
    except ValueError:
        return None


def money_in(text):
    return {n for n in (_num(m) for m in _MONEY.findall(str(text or "").translate(_AR_DIGITS))) if n is not None}


def check(reply, allowed_money=()):
    """List of violation codes (empty = clean). allowed_money: riyal figures we may say."""
    t = str(reply or "").translate(_AR_DIGITS)
    bad = []
    if _COUNT.search(t):
        bad.append("COUNT")
    if _BOOKED.search(t):
        bad.append("BOOKED")
    if _READY.search(t):
        bad.append("READY")
    allowed = {int(a) for a in allowed_money if a is not None}
    if any(n not in allowed for n in money_in(t)):
        bad.append("PRICE")
    if _PLACEHOLD.search(t):
        bad.append("PLACEHOLD")
    return bad
