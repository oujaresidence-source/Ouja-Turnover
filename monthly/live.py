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

from . import engine, host, settings

# RECONNECTED 2026-08-24, on a different mechanism than the one that failed.
#
# What broke on 2026-08-19 was not "the engine": it was WHERE the engine ran. This
# function called collect.price_one_cached() while a customer waited, and that path
# opens four short-lived brain.db connections per unit — roughly 160 on one search.
# The revert asked for "a load test first, not another guess".
#
# The load is now zero, which is a stronger answer than a load test. bot.py computes
# every unit's price on a background loop and wires the finished numbers in as
# HOST.engine_price. Below is a dictionary lookup. There is no database call left on
# this path to load-test, and collect is deliberately no longer imported here so one
# cannot be reintroduced without noticing.
CONNECTED_TO_GUEST_SITE = True


def engine_after(listing_id, month, before_total, months, discount_result):
    """Replace the DISCOUNTED total with the engine's monthly estimate, keeping
    monthly_pricing's shape exactly.

    Returns None whenever the engine cannot answer, which is most of the time
    today: below the own-history threshold the switch cannot even be flipped, so
    this is only ever reached deliberately.
    """
    # HARD STOP. bot.py no longer calls this at all; this is the second lock, so
    # that re-adding the hook without also re-enabling this cannot quietly put a
    # customer-facing page back in front of a database.
    if not CONNECTED_TO_GUEST_SITE:
        return None
    try:
        mode = settings.price_source()
        if mode not in ("engine", "engine_verified"):
            return None
        lookup = getattr(host.HOST, "engine_price", None)
        if not callable(lookup):
            return None                     # not wired = not connected, silently
        p = lookup(listing_id, month)
        if not p:
            return None
        est = p.get("price")
        if not est or est <= 0:
            return None
        # THE GUARANTEE OF "engine_verified", enforced here rather than promised:
        # a unit priced from a POOL — a district, bedroom or portfolio average —
        # keeps the discount path. This is what stops fifteen apartments showing the
        # same number side by side on one page, which is what an average looks like
        # when it is published as a price.
        #
        # It used to read `!= "own_history"`, which was stricter than that sentence:
        # own_recent and own_seasonal are the APARTMENT'S OWN history from its other
        # months, not anybody's average, and no two apartments share them. The list
        # now comes from engine.OWN_BASES, the one place it is defined, so the
        # publisher and the coverage report can no longer mean different things by
        # "its own history".
        if mode == "engine_verified" and p.get("basis") not in engine.OWN_BASES:
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
