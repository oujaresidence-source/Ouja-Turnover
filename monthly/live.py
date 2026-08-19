# -*- coding: utf-8 -*-
"""
monthly.live — the bridge to the LIVE guest site at /monthly.

THE CONTRACT, AND WHY IT IS THE WHOLE DESIGN. bot.py's monthly_pricing() returns
exactly nine keys, and the search page, the detail page, the quote endpoint and
the WhatsApp message all read them. So the engine path returns THE SAME NINE
KEYS, with the same types, and a test asserts it. Get that right and the switch
touches one function; get it wrong and it touches the whole site.

FAILS TO DISCOUNT, ALWAYS. Any exception, any missing price, any doubt returns
None and the caller keeps its existing behaviour. A pricing engine that can take
the guest site down is worse than no pricing engine — and this one is switched
off by default anyway.
"""

from . import settings


def engine_after(listing_id, month, before_total, months, discount_result):
    """Replace the DISCOUNTED total with the engine's monthly estimate, keeping
    monthly_pricing's shape exactly.

    Returns None whenever the engine cannot answer, which is most of the time
    today: below the own-history threshold the switch cannot even be flipped, so
    this is only ever reached deliberately.
    """
    try:
        mode = settings.price_source()
        if mode not in ("engine", "engine_verified"):
            return None
        from . import collect
        p = collect.price_one(int(listing_id), month)
        est = p.get("price")
        if not est or est <= 0:
            return None
        # THE GUARANTEE OF "engine_verified", enforced here rather than promised:
        # a unit priced from a district or bedroom pool keeps the discount path.
        # This is what stops fifteen apartments showing the same number side by
        # side on one page, which is what an average looks like when it is
        # published as a price.
        if mode == "engine_verified" and p.get("basis") != "own_history":
            return None

        months = max(1, int(months or 1))
        before = int(round(float(before_total or 0)))
        after = int(round(est * months))
        if before <= 0 or after <= 0:
            return None
        # A monthly offer that costs the guest MORE than booking the nights
        # outright is not an offer. The engine's ceiling already prevents it, but
        # the live site is the one place where being wrong is public.
        if after >= before:
            return None

        out = dict(discount_result)
        out["after"] = after
        out["saved"] = before - after
        out["pct"] = round((before - after) / float(before), 4)
        out["per_month_before"] = int(round(before / months))
        out["per_month_after"] = int(round(after / months))
        return out
    except Exception:
        return None
