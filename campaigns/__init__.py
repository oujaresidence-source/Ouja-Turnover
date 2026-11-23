# -*- coding: utf-8 -*-
"""
campaigns — «حملات عوجا» stage 1: the campaign engine around the Hatif WhatsApp templates.

    (1) Code-word watcher  — a Hostaway guest message carrying a code word («عرض نص» …) posts
        an alert in «عروض-خاصة» with the guest, the unit, the dates, the Sun–Wed and
        next-night checks and a ready Special Offer price (night 1 at the calendar price,
        night 2 at 50 %, never under the unit's minimum). Hostaway has NO special-offer API:
        a person sends it from the Hostaway inbox within 15 minutes.
    (2) Hatif button taps   — «إيه، كلموني» → «طلبات-الملاك» (call within 2 hours);
        «وريني الشقق» → «عروض-خاصة» + the live availability list prepared; «وش إيليت؟» → a
        canned answer prepared; «وريني الباقات» → «عروض-خاصة»; «إيقاف العروض» (or a typed
        «ايقاف» / «stop») → the persistent opt-out list in brain.db.
    (3) Weekly report       — Sunday 09:00 Riyadh: hits per code word, taps per template,
        opt-outs, and how many led to a booking within 7 days.

Layout (hatif/ pattern): config.py (env + the editable dicts) · engine.py (PURE) · db.py
(campaign_* tables in brain.db) · service.py (the three jobs) · routes.py (status) · host.py.

THE RULES — do not simplify:
    * Nothing here writes to Hostaway, and nothing messages a guest unless
      CAMPAIGN_BUTTONS_DRYRUN=0 AND HATIF_DRYRUN=0 AND the Hatif keys work AND the number is
      allowed (HATIF_TEST_NUMBERS) AND not opted out AND no staff member holds the chat.
    * No phone number is stored or posted: a salted HMAC (engine.phone_key) + last 4 digits.
    * An interactive tap that is not one of OUR labels belongs to the Hatif menu flow and is
      left alone (on_hatif returns False).
    * One alert per Hostaway message id, one row per Hatif event id (retries, two bot copies).
    * The weekly report is latched by compare-and-set in campaign_settings, never by
      @tasks.loop(time=…) (a redeploy re-runs a loop's first iteration).
    * Never state how many apartments Ouja has (the availability text comes from hatif.engine,
      which already obeys that rule).
"""
from . import config, db, engine, routes, service  # noqa: F401
from .host import HOST, wire  # noqa: F401
from .routes import register_routes  # noqa: F401


def bootstrap():
    db._ensure()
    db.salt()
    return {"watch": config.watch_enabled(), "buttons": config.buttons_enabled(),
            "buttons_dryrun": config.buttons_dryrun(), "report": config.report_enabled()}
