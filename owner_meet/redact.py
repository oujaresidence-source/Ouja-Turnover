# -*- coding: utf-8 -*-
"""
owner_meet.redact — PURE. Strips guest identity, staff names and identifiers out of free text
before it can reach an owner-facing surface (R3, R4).

    guest names  -> «الضيف»      staff names -> «فريق عوجا»
    reservation codes (HM…), Saudi phones, long digit runs, e-mails -> removed

A maintenance summary written by staff can carry the guest's name (review-call tickets are built
from it); an RR item line can carry a code. This runs on every such field at BUILD time; the
privacy scan then re-checks the rendered page and fails closed (owner_meet.privacy).
No backslashes in this file (brief P3): character classes are built from chr() at import.
"""

import re

AR = chr(0x0600) + "-" + chr(0x06FF)
WORD = "A-Za-z" + AR
_CODE = re.compile("HM[A-Z0-9]{8}")
_PHONE = re.compile("(?:[+]?966|00966|0)?5[0-9]{8}")
_DIGITS = re.compile("[0-9]{9,}")
_EMAIL = re.compile("[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,}")
_SPACES = re.compile("[ ]{2,}")
STOP = {"الضيف", "ضيف", "الشقة", "شقة", "عوجا", "Ouja", "ouja", "the", "and", "guest", "ops", "team", "admin",
        "مع", "من", "على", "في", "فريق"}


def _tokens(name):
    return [t for t in re.split("[^" + WORD + "]+", str(name or "")) if len(t) >= 3 and t.lower() not in STOP]


def tokens(name, min_len=4):
    return [t for t in _tokens(name) if len(t) >= min_len]


LATIN = "A-Za-z"
# Arabic glues one-letter words to the next one («وKhalid», «لأحمد»): a name may follow و ف ب ل ك.
_AR_PREFIX = "وفبلك"


def bounded(term):
    """A whole-word pattern for one name, aware of the script it is written in.
    Latin names: no Latin letter on either side (an Arabic letter right before is fine — «وKhalid»).
    Arabic names: no Arabic letter on either side, except up to two attached prefix letters («ولنورة»)."""
    esc = re.escape(term)
    if re.search("[" + AR + "]", term):
        one = "(?<=[" + _AR_PREFIX + "])(?<![" + AR + "][" + _AR_PREFIX + "])"
        two = "(?<=[" + _AR_PREFIX + "][" + _AR_PREFIX + "])(?<![" + AR + "][" + _AR_PREFIX + "][" + _AR_PREFIX + "])"
        before = "(?:(?<![" + AR + "])|" + one + "|" + two + ")"
        return before + esc + "(?![" + AR + "])"
    return "(?<![" + LATIN + "])" + esc + "(?![" + LATIN + "])"


def _name_pattern(names):
    """One alternation of whole names first, then their tokens, each matched as a whole word."""
    full = sorted({str(n).strip() for n in names if n and len(str(n).strip()) >= 3}, key=len, reverse=True)
    toks = sorted({t for n in names for t in _tokens(n)}, key=len, reverse=True)
    parts = [bounded(x) for x in full + toks]
    if not parts:
        return None
    return re.compile("(?:" + "|".join(parts) + ")", re.I)


_REPEAT = re.compile("(الضيف|فريق عوجا)(?:[ ،,]+[(]?(?:الضيف|فريق عوجا)[)]?)+")


class Redactor(object):
    def __init__(self, guest_names=(), staff_names=()):
        self.guest = _name_pattern(guest_names)
        self.staff = _name_pattern(staff_names)

    def __call__(self, text):
        if text is None:
            return None
        t = str(text)
        t = _EMAIL.sub("", t)
        t = _CODE.sub("", t)
        t = _PHONE.sub("", t)
        t = _DIGITS.sub("", t)
        if self.staff is not None:
            t = self.staff.sub("فريق عوجا", t)
        if self.guest is not None:
            t = self.guest.sub("الضيف", t)
        t = _REPEAT.sub(lambda m: m.group(1), t)
        return _SPACES.sub(" ", t).strip(" ،,-:")


def first_name(full):
    """The first name Airbnb shows publicly on a review — nothing more."""
    toks = [t for t in re.split("[ ]+", str(full or "").strip()) if t]
    return toks[0] if toks else ""
