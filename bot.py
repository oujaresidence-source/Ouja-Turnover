#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ouja Turnover Bot
=================
Watches Hostaway for upcoming checkouts and, 12 hours before each one, opens a
Discord channel named after the unit's internal name. The channel shows the
guest name + checkout time and has a "✅ Cleaning Done" button. When a cleaner
taps it, the channel is deleted instantly.

Runs 24/7 (e.g. on Railway). All secrets come from environment variables —
never hard-code them in this file.

Required environment variables:
  HOSTAWAY_ACCOUNT_ID   your Hostaway account id (e.g. 147296)
  HOSTAWAY_API_KEY      your Hostaway API key
  DISCORD_TOKEN         the bot token from the Discord Developer Portal
  DISCORD_GUILD_ID      your Discord server id (right-click server -> Copy Server ID)

Optional (sensible defaults):
  HOURS_AHEAD           how many hours before checkout to open the channel (default 12)
  POLL_MINUTES          how often to check Hostaway (default 15)
  TIMEZONE              default "Asia/Riyadh"
  CATEGORY_NAME         Discord category to group channels (default "🧹 Turnovers")
  DEFAULT_CHECKOUT_HOUR used if a reservation has no checkout time (default 12)
"""

import os
import re
import io
import json
import time
import random
import asyncio
from collections import defaultdict, deque, OrderedDict
from datetime import datetime, timedelta, time as dt_time
from zoneinfo import ZoneInfo

import requests
import discord
from discord.ext import commands, tasks

try:
    from aiohttp import web        # for the Hostaway webhook server (Stage 2)
    _HAS_AIOHTTP = True
except Exception:
    _HAS_AIOHTTP = False

# ---------------- config ----------------
HOSTAWAY_ACCOUNT_ID = os.environ.get("HOSTAWAY_ACCOUNT_ID", "")
HOSTAWAY_API_KEY    = os.environ.get("HOSTAWAY_API_KEY", "")
DISCORD_TOKEN       = os.environ.get("DISCORD_TOKEN", "")
GUILD_ID            = int(os.environ.get("DISCORD_GUILD_ID", "0") or "0")

HOURS_AHEAD          = int(os.environ.get("HOURS_AHEAD", "12"))
POLL_MINUTES         = int(os.environ.get("POLL_MINUTES", "15"))
TZ                   = ZoneInfo(os.environ.get("TIMEZONE", "Asia/Riyadh"))
CATEGORY_NAME        = os.environ.get("CATEGORY_NAME", "🧹 Turnovers")
# Category for the guest-assistant + escalations channels (your existing ops category).
ASSISTANT_CATEGORY   = os.environ.get("ASSISTANT_CATEGORY", "Operations")
DEFAULT_CHECKOUT_HOUR = int(os.environ.get("DEFAULT_CHECKOUT_HOUR", "12"))

# ---- last-minute tiered discount (all Riyadh time) ----
# Tier 1 fires at midnight, Tier 2 deepens it at noon, Tier 3 deepens again at 4 PM.
DISCOUNT_TIER1_PERCENT = float(os.environ.get("DISCOUNT_TIER1_PERCENT", "15"))
DISCOUNT_TIER1_HOUR    = int(os.environ.get("DISCOUNT_TIER1_HOUR", "0"))    # 00:00 = midnight
DISCOUNT_TIER2_PERCENT = float(os.environ.get("DISCOUNT_TIER2_PERCENT", "20"))
DISCOUNT_TIER2_HOUR    = int(os.environ.get("DISCOUNT_TIER2_HOUR", "12"))   # 12:00 = noon
DISCOUNT_TIER3_PERCENT = float(os.environ.get("DISCOUNT_TIER3_PERCENT", "30"))
DISCOUNT_TIER3_HOUR    = int(os.environ.get("DISCOUNT_TIER3_HOUR", "18"))   # 18:00 = 6 PM
DISCOUNT_DRY_RUN = os.environ.get("DISCOUNT_DRY_RUN", "1") not in ("0", "false", "False", "no")
DISCOUNT_FLOOR   = float(os.environ.get("DISCOUNT_FLOOR", "0") or "0")      # 0 = no floor
DISCOUNT_CHANNEL = os.environ.get("DISCOUNT_CHANNEL", "pricing-log")        # summary channel
DISCOUNT_STATE_FILE_NAME = "discount_state.json"                            # path resolved via _state_path() below (survives redeploys)
# Diagnostics: after each live write, re-read the day and log requested vs actual price.
DISCOUNT_VERIFY  = os.environ.get("DISCOUNT_VERIFY", "0") in ("1", "true", "True", "yes")
# Set to a percent (e.g. "15") to run one tier immediately on startup for testing.
DISCOUNT_TEST    = os.environ.get("DISCOUNT_TEST", "0")

# ---- 9 PM heads-up: preview tomorrow's still-empty units (3h before the midnight tier) ----
HEADS_UP_HOUR    = int(os.environ.get("HEADS_UP_HOUR", "21"))               # 21:00 = 9 PM Riyadh
HEADS_UP_CHANNEL = os.environ.get("HEADS_UP_CHANNEL", "discount-heads-up")  # where the preview is posted
HEADS_UP_TEST    = os.environ.get("HEADS_UP_TEST", "0") in ("1", "true", "True", "yes")  # post once on startup
# ---- Weekly Revenue Report (recommend-only; optimizes for max total revenue) ----
REVENUE_CHANNEL     = os.environ.get("REVENUE_CHANNEL", "revenue-report")
REVENUE_REPORT_DOW  = int(os.environ.get("REVENUE_REPORT_DOW", "6"))    # 0=Mon … 6=Sun
REVENUE_REPORT_HOUR = int(os.environ.get("REVENUE_REPORT_HOUR", "9"))   # Riyadh hour to post
REVENUE_MAX_PAGES   = int(os.environ.get("REVENUE_MAX_PAGES", "60"))    # 100 reservations/page
REVENUE_WINDOW_DAYS = int(os.environ.get("REVENUE_WINDOW_DAYS", "90"))  # trailing perf window
REVENUE_TEST        = os.environ.get("REVENUE_TEST", "0") in ("1", "true", "True", "yes")  # post once on startup
REVENUE_DEBUG       = os.environ.get("REVENUE_DEBUG", "0") in ("1", "true", "True", "yes")
# ---- Per-date pricing opportunities (#price-opportunities) ----
PRICE_OPP_CHANNEL   = os.environ.get("PRICE_OPP_CHANNEL", "price-opportunities")
PRICE_OPP_HORIZON   = int(os.environ.get("PRICE_OPP_HORIZON", "45"))    # days ahead to price
PRICE_OPP_DOW       = int(os.environ.get("PRICE_OPP_DOW", "6"))         # 0=Mon … 6=Sun
PRICE_OPP_HOUR      = int(os.environ.get("PRICE_OPP_HOUR", "10"))
PRICE_OPP_TEST      = os.environ.get("PRICE_OPP_TEST", "0") in ("1", "true", "True", "yes")
# When you click ✅ apply, the bot writes the new price to your Hostaway calendar.
# Set PRICE_APPLY_DRYRUN=1 to TEST safely (logs what it would do, changes nothing).
PRICE_APPLY_DRYRUN  = os.environ.get("PRICE_APPLY_DRYRUN", "0") in ("1", "true", "True", "yes")
# Dynamic pricing strategy: after you Apply, the bot keeps optimizing that unit's open nights
# toward the best numbers (holds high when far out; steps down as a night stays empty & nears).
PRICING_STRATEGY_ENABLED = os.environ.get("PRICING_STRATEGY_ENABLED", "1") in ("1", "true", "True", "yes")
PRICING_STRATEGY_MIN     = int(os.environ.get("PRICING_STRATEGY_MIN", "10"))   # re-optimize interval (min)
PRICE_OPP_MAX_CARDS = int(os.environ.get("PRICE_OPP_MAX_CARDS", "15"))  # action cards to post
# ---- Last-week performance review (#last-week-review) ----
WEEKLY_REVIEW_CHANNEL = os.environ.get("WEEKLY_REVIEW_CHANNEL", "last-week-review")
WEEKLY_REVIEW_DOW   = int(os.environ.get("WEEKLY_REVIEW_DOW", "6"))     # 0=Mon … 6=Sun
WEEKLY_REVIEW_HOUR  = int(os.environ.get("WEEKLY_REVIEW_HOUR", "8"))
WEEKLY_REVIEW_TEST  = os.environ.get("WEEKLY_REVIEW_TEST", "0") in ("1", "true", "True", "yes")

# ---- weekend rule (Thu/Fri): no midnight/noon tiers — a single softer discount at 5:30 PM ----
WEEKEND_DAYS = set(int(x) for x in os.environ.get("WEEKEND_DAYS", "3,4").split(",")
                   if x.strip().isdigit())                                  # 3=Thu, 4=Fri (Mon=0)
WEEKEND_DISCOUNT_PERCENT = float(os.environ.get("WEEKEND_DISCOUNT_PERCENT", "20"))
WEEKEND_DISCOUNT_HOUR    = int(os.environ.get("WEEKEND_DISCOUNT_HOUR", "17"))
WEEKEND_DISCOUNT_MINUTE  = int(os.environ.get("WEEKEND_DISCOUNT_MINUTE", "30"))  # 17:30 = 5:30 PM

# ---- cleaning reminders: nag the open turnover channels until ✅ Cleaning Done ----
REMINDER_START_HOUR = int(os.environ.get("REMINDER_START_HOUR", "12"))  # start at 12 PM
REMINDER_FAST_HOUR  = int(os.environ.get("REMINDER_FAST_HOUR", "15"))   # speed up at 3 PM
REMINDER_END_HOUR   = int(os.environ.get("REMINDER_END_HOUR", "23"))    # stop at 11 PM
REMINDER_SLOW_MIN   = int(os.environ.get("REMINDER_SLOW_MIN", "30"))    # 12 PM–3 PM: every 30 min
REMINDER_FAST_MIN   = int(os.environ.get("REMINDER_FAST_MIN", "15"))    # after 3 PM: every 15 min
OPERATION_ROLE_ID   = os.environ.get("OPERATION_ROLE_ID", "")           # role to ping if no cleaner
OPERATION_ROLE_NAME = os.environ.get("OPERATION_ROLE_NAME", "operation")

# ---- AI guest-message assistant (Claude drafts, a human approves, then it sends) ----
ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL       = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
# Smarter model for the few high-touch, personality-heavy messages (manager script +
# empathetic repeat-escalation acks). Low volume, so the extra cost is tiny.
CLAUDE_MODEL_PREMIUM = os.environ.get("CLAUDE_MODEL_PREMIUM", "claude-sonnet-4-6")
ASSISTANT_ENABLED  = os.environ.get("ASSISTANT_ENABLED", "0") in ("1", "true", "True", "yes")
ASSISTANT_CHANNEL  = os.environ.get("ASSISTANT_CHANNEL", "guest-assistant")
ASSISTANT_POLL_MIN = float(os.environ.get("ASSISTANT_POLL_MIN", "0.5"))   # check inbox every N min (float ok)
ASSISTANT_SCAN     = int(os.environ.get("ASSISTANT_SCAN", "30"))      # how many recent convos to scan
# ---- Stage 2: Hostaway webhooks (instant replies). 100% optional/backward-compatible:
# if not set up in Hostaway, the bot just keeps polling as before. ----
WEBHOOKS_ENABLED = os.environ.get("WEBHOOKS_ENABLED", "1") in ("1", "true", "True", "yes")
WEBHOOK_SECRET   = os.environ.get("WEBHOOK_SECRET", "ouja-hook")      # the secret path segment
WEB_PORT         = int(os.environ.get("PORT", "8080"))               # Railway provides PORT
# ---- Web dashboard (served by the same bot at /dashboard). Protected by a token. ----
DASHBOARD_ENABLED = os.environ.get("DASHBOARD_ENABLED", "1") in ("1", "true", "True", "yes")
DASHBOARD_TOKEN   = os.environ.get("DASHBOARD_TOKEN", "")            # REQUIRED to view (set your own)
DASH_TTL          = int(os.environ.get("DASH_TTL", "600"))          # cache computed analytics (sec)
DASH_REFRESH_MIN  = int(os.environ.get("DASH_REFRESH_MIN", "7"))    # background pre-compute interval (min)
# Safety: replies are NEVER sent automatically unless you explicitly turn this on later.
ASSISTANT_AUTOSEND = os.environ.get("ASSISTANT_AUTOSEND", "0") in ("1", "true", "True", "yes")
ASSISTANT_DEBUG    = os.environ.get("ASSISTANT_DEBUG", "0") in ("1", "true", "True", "yes")
# Skip the startup "mark everything seen" baseline so the latest unanswered guest
# messages get drafted right away (handy for a first test without sending a new message).
ASSISTANT_TEST     = os.environ.get("ASSISTANT_TEST", "0") in ("1", "true", "True", "yes")
# On startup, messages newer than this many minutes are NOT baselined, so a fresh guest
# message still gets a card even if the bot just restarted/redeployed. Set 0 to baseline all.
ASSISTANT_BASELINE_GRACE_MIN = int(os.environ.get("ASSISTANT_BASELINE_GRACE_MIN", "15"))
# Also draft a reply when the only thing sent AFTER the guest's question is an automated
# welcome/booking message (so guest questions buried under auto-messages still get answered).
# A real human/bot reply after the guest still counts as "answered" and is skipped.
ASSISTANT_ANSWER_PAST_AUTO = os.environ.get("ASSISTANT_ANSWER_PAST_AUTO", "1") in ("1", "true", "True", "yes")
# Outbound messages containing any of these (case-insensitive, '|'-separated) are treated as
# automated, not a real answer. Add your Hostaway welcome/automation phrases here.
AUTO_REPLY_MARKERS = [m.strip() for m in os.environ.get(
    "AUTO_REPLY_MARKERS", "truly delighted|we are truly|delighted by your|we've prepared|we have prepared").split("|") if m.strip()]
# Always draft a card for the guest's latest message, even if the team/automation already
# replied after it. Set 0 to only draft when the guest is unanswered.
ASSISTANT_ALWAYS_DRAFT = os.environ.get("ASSISTANT_ALWAYS_DRAFT", "1") in ("1", "true", "True", "yes")
# Knowledge base: a Discord channel the assistant reads as facts about Ouja. Anyone can add
# facts by typing in it, and the 🧠 Teach button on a card saves corrections here.
KNOWLEDGE_CHANNEL     = os.environ.get("KNOWLEDGE_CHANNEL", "knowledge")
KNOWLEDGE_REFRESH_MIN = int(os.environ.get("KNOWLEDGE_REFRESH_MIN", "5"))
KNOWLEDGE_MAX         = int(os.environ.get("KNOWLEDGE_MAX", "300"))   # facts (messages) to load
# When on, logs each listing's active-status + whether an Airbnb link was found (for tuning).
CATALOG_DEBUG = os.environ.get("CATALOG_DEBUG", "0") in ("1", "true", "True", "yes")
# Pull a real "starting from" nightly price from each unit's calendar (reflects dynamic pricing).
CATALOG_CALENDAR_PRICES = os.environ.get("CATALOG_CALENDAR_PRICES", "1") in ("1", "true", "True", "yes")
# Auto-send: when ON, very simple/safe replies (action="auto") go straight to the guest;
# anything needing approval or a human still posts a card. Default OFF — everything waits
# for approval/edit until you've judged the assistant's quality. Set to 1 to enable later.
ASSISTANT_AUTO     = os.environ.get("ASSISTANT_AUTO", "0") in ("1", "true", "True", "yes")
ASSISTANT_AUTO_CONF = float(os.environ.get("ASSISTANT_AUTO_CONF", "0.85"))  # Stage 1: auto-send at/above this confidence
ESCALATE_BELOW     = float(os.environ.get("ESCALATE_BELOW", "0.55"))       # Stage 3: escalate below this confidence
# Signature appended to every guest-facing message.
ASSISTANT_SIGNATURE_AR = os.environ.get("ASSISTANT_SIGNATURE_AR", "الدعم الفني - مساعد 🤍")
ASSISTANT_SIGNATURE_EN = os.environ.get("ASSISTANT_SIGNATURE_EN", "Technical Support - Musaid 🤍")
# When a chat escalates to a human, auto-send the guest a holding message.
ASSISTANT_ESC_ACK  = os.environ.get("ASSISTANT_ESC_ACK", "1") in ("1", "true", "True", "yes")
ASSISTANT_ACK_AR   = os.environ.get("ASSISTANT_ACK_AR",
    "حياك الله 🤍 رفعنا موضوعك للقسم المختص، وبيتواصل معك الفريق في أقرب وقت.")
ASSISTANT_ACK_EN   = os.environ.get("ASSISTANT_ACK_EN",
    "Thank you 🤍 We've escalated this to our specialized team and someone will contact you shortly.")
# Escalations go to their own channel, ping the operation team, and re-ping until claimed.
ESCALATION_CHANNEL    = os.environ.get("ESCALATION_CHANNEL", "escalations")
AUTO_REPLY_CHANNEL    = os.environ.get("AUTO_REPLY_CHANNEL", "auto-replies")  # audit log of Stage-1 auto-sends
ESCALATION_REPING_MIN = int(os.environ.get("ESCALATION_REPING_MIN", "10"))   # re-ping every N min
ESCALATION_MAX_PINGS  = int(os.environ.get("ESCALATION_MAX_PINGS", "12"))    # stop after this many re-pings
CLAIM_NAMES = [n.strip() for n in os.environ.get(
    "CLAIM_NAMES", "اسيل,فيصل,ماثر,نوره,ناصر,محمد").split(",") if n.strip()]
# When someone claims an escalation, DM them a ready-to-send reply in the owner's warm style.
MANAGER_SCRIPT = os.environ.get("MANAGER_SCRIPT", "1") in ("1", "true", "True", "yes")

BASE = "https://api.hostaway.com/v1"
GOLD = 0xC8A24B

# ---------------- bounded helpers ----------------
class _BoundedSet:
    """Insertion-ordered set with a hard cap. Oldest entries auto-evicted.
    Used for `_assistant_seen` so we don't (a) grow forever in memory or
    (b) lose recent message IDs when an unordered set is sliced on save."""
    __slots__ = ("_d", "maxlen")

    def __init__(self, items=(), maxlen=20000):
        self._d = OrderedDict()
        self.maxlen = maxlen
        for x in items:
            self.add(x)

    def add(self, item):
        if item in self._d:
            self._d.move_to_end(item)
        else:
            self._d[item] = None
            if len(self._d) > self.maxlen:
                self._d.popitem(last=False)

    def __contains__(self, item):
        return item in self._d

    def __len__(self):
        return len(self._d)

    def __iter__(self):
        return iter(self._d)

    def __bool__(self):
        return bool(self._d)

def _bounded_cache_put(cache, key, value, maxlen):
    """Trim an OrderedDict cache to `maxlen` after inserting. Caller passes an OrderedDict."""
    if key in cache:
        cache.move_to_end(key)
    cache[key] = value
    while len(cache) > maxlen:
        cache.popitem(last=False)

# ---------------- Persistent state (Railway Volume) ----------------
# Mount a Railway Volume at this path so state survives restarts AND redeploys.
STATE_DIR = os.environ.get("STATE_DIR", "/data")

def _state_path(name):
    return os.path.join(STATE_DIR, name)

def _save_json(name, obj):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = _state_path(name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        os.replace(tmp, _state_path(name))   # atomic write
    except Exception as e:
        print(f"state save error ({name}):", e)

def _load_json(name, default):
    try:
        with open(_state_path(name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _state_persistent():
    """True if STATE_DIR looks like a mounted volume (writable & exists)."""
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        return os.path.isdir(STATE_DIR)
    except Exception:
        return False

HANDLED_FILE = _state_path("handled.json")

# ---------------- Hostaway ----------------
_token = {"value": None}

def get_token(force=False):
    if _token["value"] and not force:
        return _token["value"]
    r = requests.post(
        f"{BASE}/accessTokens",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials", "client_id": HOSTAWAY_ACCOUNT_ID,
              "client_secret": HOSTAWAY_API_KEY, "scope": "general"},
        timeout=30,
    )
    r.raise_for_status()
    _token["value"] = r.json()["access_token"]
    return _token["value"]

# Status codes that mean "your bearer token is no longer accepted — refresh once and retry."
# Hostaway has been observed to use 403; spec says 401 — accept both to be safe.
_AUTH_RETRY_CODES = (401, 403)

def api_get(path, params=None, _retry=0):
    token = get_token()
    r = requests.get(
        f"{BASE}{path}",
        headers={"Authorization": f"Bearer {token}", "Cache-control": "no-cache"},
        params=params or {}, timeout=60,
    )
    if r.status_code in _AUTH_RETRY_CODES and _retry == 0:   # token expired -> refresh once
        get_token(force=True)
        return api_get(path, params, _retry + 1)
    if r.status_code == 429:                          # rate limited -> brief backoff
        time.sleep(10)
        if _retry < 3:
            return api_get(path, params, _retry + 1)
    r.raise_for_status()
    return r.json()

def api_post(path, body, _retry=0):
    token = get_token()
    r = requests.post(
        f"{BASE}{path}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "Cache-control": "no-cache"},
        json=body, timeout=60,
    )
    if r.status_code in _AUTH_RETRY_CODES and _retry == 0:
        get_token(force=True)
        return api_post(path, body, _retry + 1)
    if r.status_code == 429:
        time.sleep(10)
        if _retry < 3:
            return api_post(path, body, _retry + 1)
    r.raise_for_status()
    return r.json()


def api_put(path, body, _retry=0):
    token = get_token()
    r = requests.put(
        f"{BASE}{path}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "Cache-control": "no-cache"},
        json=body, timeout=60,
    )
    if r.status_code in _AUTH_RETRY_CODES and _retry == 0:
        get_token(force=True)
        return api_put(path, body, _retry + 1)
    if r.status_code == 429:
        time.sleep(10)
        if _retry < 3:
            return api_put(path, body, _retry + 1)
    r.raise_for_status()
    return r.json()

_listings = {"map": {}, "ts": 0}

def get_listings_map():
    """listingMapId -> internal name (cached for 1 hour)."""
    if _listings["map"] and time.time() - _listings["ts"] < 3600:
        return _listings["map"]
    m, limit, offset = {}, 100, 0
    while True:
        data = api_get("/listings", params={"limit": limit, "offset": offset})
        batch = data.get("result", []) or []
        for l in batch:
            m[l.get("id")] = l.get("internalListingName") or l.get("name") or f"unit-{l.get('id')}"
        if len(batch) < limit:
            break
        offset += limit
    _listings["map"], _listings["ts"] = m, time.time()
    return m

def parse_hour(v, default):
    if v is None:
        return default
    s = str(v)
    if ":" in s:
        try: return int(s.split(":")[0])
        except: return default
    try: return int(float(s))
    except: return default

SKIP_STATUSES = {"cancelled", "declined", "expired", "inquiry", "inquirydenied", "inquirytimedout"}

def fetch_upcoming_checkouts():
    """Reservations whose checkout falls within the next HOURS_AHEAD hours."""
    listings = get_listings_map()
    now = datetime.now(TZ)
    window_end = now + timedelta(hours=HOURS_AHEAD)
    today = now.date().isoformat()
    tomorrow = (now.date() + timedelta(days=1)).isoformat()

    out, limit, offset, pages = [], 100, 0, 0
    while pages < 10:
        data = api_get("/reservations", params={
            "departureStartDate": today, "departureEndDate": tomorrow,
            "limit": limit, "offset": offset, "includeResources": 0,
        })
        batch = data.get("result", []) or []
        if not batch:
            break
        for res in batch:
            if (res.get("status") or "").lower() in SKIP_STATUSES:
                continue
            dep = res.get("departureDate")
            if not dep:
                continue
            hour = parse_hour(res.get("checkOutTime"), DEFAULT_CHECKOUT_HOUR)
            try:
                checkout = datetime.strptime(dep[:10], "%Y-%m-%d").replace(
                    hour=min(hour, 23), tzinfo=TZ)
            except ValueError:
                continue
            if now <= checkout <= window_end:
                lm = res.get("listingMapId")
                out.append({
                    "res_id": str(res.get("id")),
                    "listing": listings.get(lm) or res.get("listingName") or f"unit-{lm}",
                    "guest": res.get("guestName") or res.get("guestFirstName") or "Guest",
                    "checkout": checkout,
                })
        if len(batch) < limit:
            break
        offset += limit
        pages += 1
    return out

def _load_discount_state():
    # _load_json returns the default on any error and reads from STATE_DIR (the volume),
    # so tonight's "original price" snapshot survives redeploys.
    return _load_json(DISCOUNT_STATE_FILE_NAME, {})

def _save_discount_state(st):
    _save_json(DISCOUNT_STATE_FILE_NAME, st)

def apply_discount_tier(pct):
    """Set tonight's price to `pct`% off the ORIGINAL price, for every still-empty unit.
    The original is captured once per day (state file + Hostaway note) so the two tiers
    never compound. Returns (changes, today). Honors DRY-RUN."""
    factor = (100.0 - pct) / 100.0
    today = datetime.now(TZ).date().isoformat()
    state = _load_discount_state()
    state = {today: state.get(today, {})}      # keep only today's record
    day_orig = state[today]
    listings = get_listings_map()
    changes = []
    for lid, name in listings.items():
        lid_s = str(lid)
        if is_unit_skipped(lid):
            continue                                       # owner asked to hold price on this unit
        try:
            cal = api_get(f"/listings/{lid}/calendar",
                          params={"startDate": today, "endDate": today})
            days = cal.get("result", []) or []
            if not days:
                continue
            d = days[0]
            available = int(d.get("isAvailable", 0) or 0) == 1
            booked = bool(d.get("reservationId"))
            current = d.get("price")
            if not available or booked or not current:
                continue                                   # booked / blocked / no price
            current = float(current)
            # recover tonight's original: remembered state -> Hostaway note -> current
            original = day_orig.get(lid_s)
            if original is None:
                m = re.search(r"ouja-orig:(\d+(?:\.\d+)?)", str(d.get("note") or ""))
                original = float(m.group(1)) if m else current
                day_orig[lid_s] = original
            new_price = round(original * factor)
            if DISCOUNT_FLOOR and new_price < DISCOUNT_FLOOR:
                new_price = int(DISCOUNT_FLOOR)
            if new_price >= current:
                continue                                   # already at/below this level
            if not DISCOUNT_DRY_RUN:
                resp = api_put(f"/listings/{lid}/calendar",
                        {"startDate": today, "endDate": today,
                         "isAvailable": 1, "price": new_price,
                         "note": f"ouja-orig:{int(original)}"})
                if DISCOUNT_VERIFY:
                    try:
                        chk = api_get(f"/listings/{lid}/calendar",
                                      params={"startDate": today, "endDate": today})
                        cd = (chk.get("result") or [{}])[0]
                        actual = cd.get("price")
                        status = resp.get("status") if isinstance(resp, dict) else "?"
                        stuck = "✅ stuck" if str(actual) == str(new_price) else "❌ reverted/ignored"
                        print(f"   VERIFY {name}: requested {new_price}, Hostaway now shows "
                              f"{actual} ({stuck}) · PUT status={status}")
                    except Exception as e:
                        print(f"   VERIFY {name}: read-back failed: {e}")
            changes.append({"name": name, "orig": int(original),
                            "old": int(current), "new": int(new_price)})
        except Exception as e:
            print(f"discount error for {name}: {e}")
    _save_discount_state(state)
    return changes, today

def is_weekend_today():
    return datetime.now(TZ).weekday() in WEEKEND_DAYS

def compute_tonight_empty():
    """For each unit empty TONIGHT, return its current price + the discount schedule the
    bot will apply if the unit stays empty (tier 1 at midnight, 2 at noon, 3 at 6 PM, or
    a single weekend drop on Thu/Fri at 5:30 PM). Also includes the owner-set skip status.

    Returned shape (one entry per empty unit):
      {lid, name, price, t1, t2, t3, w, weekend, skipped_until, paused_global,
       tier_times: [{label, hour, minute, pct, price}], next: {label, when_iso, price}}
    """
    today = datetime.now(TZ).date()
    today_iso = today.isoformat()
    weekend = today.weekday() in WEEKEND_DAYS
    listings = get_listings_map()
    now = datetime.now(TZ)
    paused_global = is_discount_paused()

    f1 = (100.0 - DISCOUNT_TIER1_PERCENT) / 100.0
    f2 = (100.0 - DISCOUNT_TIER2_PERCENT) / 100.0
    f3 = (100.0 - DISCOUNT_TIER3_PERCENT) / 100.0
    fw = (100.0 - WEEKEND_DISCOUNT_PERCENT) / 100.0

    items = []
    for lid, name in listings.items():
        try:
            cal = api_get(f"/listings/{lid}/calendar",
                          params={"startDate": today_iso, "endDate": today_iso})
            days = cal.get("result", []) or []
            if not days:
                continue
            d = days[0]
            available = int(d.get("isAvailable", 0) or 0) == 1
            booked = bool(d.get("reservationId"))
            price = d.get("price")
            if not available or booked or not price:
                continue
            price = float(price)
            # recover the original (anchor) so the tier prices we show match what the
            # discount loop would actually write.
            m = re.search(r"ouja-orig:(\d+(?:\.\d+)?)", str(d.get("note") or ""))
            original = float(m.group(1)) if m else price

            tier_times = []
            if weekend:
                tier_times.append({"label": "Weekend",
                                   "hour": WEEKEND_DISCOUNT_HOUR, "minute": WEEKEND_DISCOUNT_MINUTE,
                                   "pct": int(WEEKEND_DISCOUNT_PERCENT),
                                   "price": int(round(original * fw))})
            else:
                tier_times.append({"label": "T1", "hour": DISCOUNT_TIER1_HOUR, "minute": 0,
                                   "pct": int(DISCOUNT_TIER1_PERCENT),
                                   "price": int(round(original * f1))})
                tier_times.append({"label": "T2", "hour": DISCOUNT_TIER2_HOUR, "minute": 0,
                                   "pct": int(DISCOUNT_TIER2_PERCENT),
                                   "price": int(round(original * f2))})
                tier_times.append({"label": "T3", "hour": DISCOUNT_TIER3_HOUR, "minute": 0,
                                   "pct": int(DISCOUNT_TIER3_PERCENT),
                                   "price": int(round(original * f3))})

            # which tier is "next" today (still upcoming)?
            next_tier = None
            for tt in tier_times:
                fire = now.replace(hour=tt["hour"], minute=tt["minute"], second=0, microsecond=0)
                if fire > now:
                    next_tier = {"label": tt["label"], "when_iso": fire.isoformat(timespec="minutes"),
                                 "pct": tt["pct"], "price": tt["price"]}
                    break

            items.append({
                "lid": lid, "name": name,
                "price": int(round(price)), "original": int(round(original)),
                "t1": int(round(original * f1)), "t2": int(round(original * f2)),
                "t3": int(round(original * f3)), "w": int(round(original * fw)),
                "weekend": weekend, "tier_times": tier_times, "next": next_tier,
                "skipped_until": unit_skip_until_iso(lid),
                "paused_global": paused_global,
            })
        except Exception as e:
            print(f"tonight-empty error for {name}: {e}")
    items.sort(key=lambda x: x["name"])
    return items

def get_inbox_item_detail(item_id):
    """Build a rich detail view for a pending reply or open escalation, including the
    full conversation history (refetched from Hostaway) and the booking context."""
    try:
        item_id = int(item_id)
    except Exception:
        return None
    src = None; kind = None
    if item_id in _pending_replies:
        src = _pending_replies[item_id]; kind = "reply"
    elif item_id in _escalations:
        src = _escalations[item_id]; kind = "escalation"
    if not src:
        return None

    if kind == "reply":
        item = src.get("item", {})
        cid = item.get("conversation_id")
        guest = item.get("guest"); unit = item.get("unit"); lid = item.get("listing_id")
        res_id = item.get("reservation_id")
        checkin = item.get("checkin"); checkout = item.get("checkout")
        draft = src.get("draft", ""); confirmed = src.get("confirmed", False)
        reason = ""; intent = src.get("intent", ""); conf = src.get("confidence")
        sentiment = src.get("sentiment", "")
    else:   # escalation
        cid = src.get("conversation_id")
        guest = src.get("guest"); unit = src.get("unit"); lid = None
        res_id = None; checkin = None; checkout = None
        draft = ""; confirmed = False
        reason = src.get("reason", ""); intent = ""; conf = None; sentiment = ""

    # refetch the live thread so the dashboard shows the latest
    thread = []
    if cid:
        try:
            data = api_get(f"/conversations/{cid}/messages")
            msgs = sorted((data.get("result") or []), key=_msg_sort_key)
            for m in msgs[-30:]:
                thread.append({
                    "from": "guest" if _msg_is_inbound(m) else "host",
                    "text": (m.get("body") or "").strip(),
                    "ts": _msg_time(m),
                    "automated": (not _msg_is_inbound(m)) and _looks_automated(m.get("body") or ""),
                })
        except Exception as e:
            print(f"detail fetch thread error ({cid}):", e)

    # booking context
    nights = None; total = None; status = ""
    if res_id:
        try:
            data = api_get(f"/reservations/{res_id}")
            r = data.get("result") or {}
            nights = _res_nights(r) or None
            total = r.get("totalPrice") or None
            status = (r.get("status") or "").lower()
            checkin = checkin or r.get("arrivalDate")
            checkout = checkout or r.get("departureDate")
        except Exception as e:
            print(f"detail fetch reservation error ({res_id}):", e)

    return {
        "kind": kind, "id": item_id, "guest": guest or "", "unit": unit or "",
        "listing_id": lid, "conversation_id": cid, "reservation_id": res_id,
        "status": status, "confirmed": confirmed,
        "checkin": checkin, "checkout": checkout, "nights": nights, "total_price": total,
        "draft": draft, "reason": reason, "intent": intent, "confidence": conf,
        "sentiment": sentiment, "thread": thread,
    }

def compute_headsup():
    """List units still empty for TOMORROW night, with the discount they'll actually get."""
    f1 = (100.0 - DISCOUNT_TIER1_PERCENT) / 100.0
    f2 = (100.0 - DISCOUNT_TIER2_PERCENT) / 100.0
    f3 = (100.0 - DISCOUNT_TIER3_PERCENT) / 100.0
    fw = (100.0 - WEEKEND_DISCOUNT_PERCENT) / 100.0
    tomorrow_date = datetime.now(TZ).date() + timedelta(days=1)
    tomorrow = tomorrow_date.isoformat()
    weekend = tomorrow_date.weekday() in WEEKEND_DAYS
    listings = get_listings_map()
    items = []
    for lid, name in listings.items():
        try:
            cal = api_get(f"/listings/{lid}/calendar",
                          params={"startDate": tomorrow, "endDate": tomorrow})
            days = cal.get("result", []) or []
            if not days:
                continue
            d = days[0]
            available = int(d.get("isAvailable", 0) or 0) == 1
            booked = bool(d.get("reservationId"))
            price = d.get("price")
            if not available or booked or not price:
                continue
            price = float(price)
            items.append({"name": name, "price": int(price),
                          "t1": int(round(price * f1)), "t2": int(round(price * f2)),
                          "t3": int(round(price * f3)), "w": int(round(price * fw))})
        except Exception as e:
            print(f"headsup error for {name}: {e}")
    return items, tomorrow, weekend

# ---------------- handled-set persistence ----------------
def load_handled():
    try:
        return set(json.load(open(HANDLED_FILE)))
    except Exception:
        return set()

def save_handled(s):
    try:
        json.dump(list(s), open(HANDLED_FILE, "w"))
    except Exception:
        pass

handled = load_handled()

# ---------------- Discord ----------------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!ouja ", intents=intents)

class CleaningDoneView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)   # persistent across restarts

    @discord.ui.button(label="✅ Cleaning Done", style=discord.ButtonStyle.success,
                       custom_id="ouja_cleaning_done")
    async def done(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            f"✅ Marked done by {interaction.user.mention}. Closing this channel…",
            ephemeral=False)
        await asyncio.sleep(2)
        try:
            await interaction.channel.delete(reason=f"Cleaning completed by {interaction.user}")
        except Exception as e:
            print("delete error:", e)

def channel_name(internal_name):
    # Discord channel names must be lowercase, no spaces/symbols.
    # "Ouja | B209" -> "ouja-b209". The full name is shown inside the channel.
    return re.sub(r"[^a-z0-9]+", "-", internal_name.lower()).strip("-")[:90] or "unit"

# ---- responsible-person lookup (from assignments.json built off the Excel) ----
try:
    ASSIGNMENTS = json.load(open("assignments.json", encoding="utf-8"))
except Exception as e:
    print("Could not load assignments.json:", e)
    ASSIGNMENTS = {"by_day": {}, "discord_ids": {}}

# Python weekday(): Mon=0 ... Sun=6
ARABIC_DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

def norm_unit(s):
    s = str(s).strip().lower().replace("ouja", "").replace("|", "")
    return re.sub(r"[\s\-_]+", " ", s).strip()

def _clip(s, n=18):
    """Trim a unit name so the table columns stay aligned."""
    s = str(s).strip()
    return s if len(s) <= n else s[:n - 1] + "…"

def _fmt_hour(h):
    """24h int -> friendly label, e.g. 0->'12 AM', 12->'12 PM', 18->'6 PM'."""
    suffix = "AM" if h < 12 else "PM"
    return f"{h % 12 or 12} {suffix}"

def parse_topic_res(topic):
    """Reservation id stored in a turnover channel's topic."""
    m = re.search(r"hostaway-res:(\d+)", topic or "")
    return m.group(1) if m else None

def parse_topic_did(topic):
    """Responsible cleaner's Discord id stored in the topic (None if unassigned)."""
    m = re.search(r"did:(\d+)", topic or "")
    return m.group(1) if m else None

def find_operation_role(guild):
    """The role to ping when a unit has no assigned cleaner."""
    if OPERATION_ROLE_ID.isdigit():
        r = guild.get_role(int(OPERATION_ROLE_ID))
        if r:
            return r
    name = OPERATION_ROLE_NAME.lower()
    for r in guild.roles:
        if r.name.lower() == name:
            return r
    return None

def responsible_for(internal_name, checkout_dt):
    """Returns (employee_name, discord_id, arabic_day). Any may be None if no match."""
    day = ARABIC_DAYS[checkout_dt.weekday()]
    emp = ASSIGNMENTS.get("by_day", {}).get(day, {}).get(norm_unit(internal_name))
    did = ASSIGNMENTS.get("discord_ids", {}).get(emp) if emp else None
    return emp, did, day

async def get_category(guild):
    for cat in guild.categories:
        if cat.name == CATEGORY_NAME:
            return cat
    return await guild.create_category(CATEGORY_NAME)

async def get_assistant_category(guild):
    """Category for guest-assistant + escalations. Reuses your existing Operations category."""
    want = ASSISTANT_CATEGORY.lower()
    for cat in guild.categories:
        if cat.name.lower() == want:
            return cat
    return await guild.create_category(ASSISTANT_CATEGORY)

async def ensure_channel(guild, name, category=None):
    """Find a text channel by name (create it if missing) and keep it under `category`."""
    ch = discord.utils.get(guild.text_channels, name=name)
    if ch is None:
        try:
            ch = await guild.create_text_channel(name, category=category)
        except Exception as e:
            print(f"channel create error ({name}):", e)
            return None
    elif category is not None and ch.category_id != category.id:
        try:
            await ch.edit(category=category)      # move existing channel under the category
        except Exception as e:
            print(f"channel move error ({name}):", e)
    return ch

async def sync_checkouts():
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        print("Guild not found — check DISCORD_GUILD_ID and that the bot was invited.")
        return
    category = await get_category(guild)

    # reservation ids that already have a live channel
    existing = set()
    for ch in category.text_channels:
        rid = parse_topic_res(ch.topic)
        if rid:
            existing.add(rid)
    handled.update(existing)

    items = await asyncio.to_thread(fetch_upcoming_checkouts)
    for it in items:
        if it["res_id"] in handled or it["res_id"] in existing:
            continue
        try:
            emp, did, day = responsible_for(it["listing"], it["checkout"])
            # topic carries the reservation id + responsible discord id (for reminders)
            topic = f"hostaway-res:{it['res_id']} did:{did or ''}"
            ch = await guild.create_text_channel(
                channel_name(it["listing"]), category=category, topic=topic)
            embed = discord.Embed(title="🧹 Turnover Ready", color=GOLD)
            embed.add_field(name="Unit", value=it["listing"], inline=False)
            embed.add_field(name="Guest", value=it["guest"], inline=True)
            embed.add_field(name="Checkout",
                            value=it["checkout"].strftime("%a %d %b · %I:%M %p"), inline=True)

            if emp:
                embed.add_field(name="مسؤول التنظيف",
                                value=(f"<@{did}> ({emp})" if did else emp), inline=False)
            embed.set_footer(text="Tap the button below once cleaning is complete to close this channel.")

            content = f"<@{did}> 🧹 وحدة جاهزة للتنظيف" if did else None
            await ch.send(content=content, embed=embed, view=CleaningDoneView(),
                          allowed_mentions=discord.AllowedMentions(users=True, roles=True))
            handled.add(it["res_id"])
            save_handled(handled)
            note = f" -> {emp}" if emp else " (no responsible match — check unit name)"
            print(f"Opened channel for {it['listing']} (res {it['res_id']}){note}")
        except Exception as e:
            print("create error:", e)

@tasks.loop(minutes=POLL_MINUTES)
async def poll_loop():
    try:
        await sync_checkouts()
    except Exception as e:
        print("poll error:", e)

# remembers when each open channel was last pinged (resets on restart, which is fine)
_last_reminder = {}

@tasks.loop(minutes=1)
async def reminder_loop():
    """Nag every open turnover channel until cleaning is marked done.
    12 PM–3 PM: every 30 min. After 3 PM: every 15 min. Quiet outside those hours."""
    now = datetime.now(TZ)
    hour = now.hour
    if hour < REMINDER_START_HOUR or hour >= REMINDER_END_HOUR:
        return
    interval = REMINDER_SLOW_MIN if hour < REMINDER_FAST_HOUR else REMINDER_FAST_MIN
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return
    category = discord.utils.get(guild.categories, name=CATEGORY_NAME)
    if category is None:
        return
    op_role = find_operation_role(guild)
    live_ids = set()
    for ch in list(category.text_channels):
        if not parse_topic_res(ch.topic):
            continue                      # only turnover channels
        live_ids.add(ch.id)
        last = _last_reminder.get(ch.id)
        if last and (now - last) < timedelta(minutes=interval):
            continue
        did = parse_topic_did(ch.topic)
        if did:
            mention = f"<@{did}>"
        elif op_role:
            mention = op_role.mention
        else:
            mention = f"@{OPERATION_ROLE_NAME}"
        try:
            await ch.send(
                f"{mention} ⏰ تذكير: هالوحدة لسه تحتاج تنظيف — اضغط ✅ Cleaning Done لما تخلص.",
                allowed_mentions=discord.AllowedMentions(users=True, roles=True))
            _last_reminder[ch.id] = now
        except Exception as e:
            print(f"reminder error ({ch.name}):", e)
    # drop timers for channels that no longer exist (cleaning done)
    for cid in list(_last_reminder.keys()):
        if cid not in live_ids:
            _last_reminder.pop(cid, None)

async def post_discount_summary(changes, today, pct, label):
    if not changes:
        return
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return
    category = await get_category(guild)
    channel = await ensure_channel(guild, DISCOUNT_CHANNEL, category)
    if channel is None:
        return
    state = ("🧪 معاينة فقط — ما تغيّر أي سعر"
             if DISCOUNT_DRY_RUN else f"✅ تم تطبيق خصم {int(pct)}٪ من السعر الأصلي")
    lines = "\n".join(f"• {c['name']}: {c['orig']} → {c['new']} ر.س" for c in changes[:60])
    embed = discord.Embed(title=f"💰 {label} · خصم {int(pct)}٪ · {today}",
                          description=lines, color=GOLD)
    embed.set_footer(text=f"{state} · {len(changes)} وحدة فاضية")
    await channel.send(embed=embed)

# Owner-controlled pause for the discount tiers. 0 = not paused; otherwise unix-timestamp
# until which all tier loops skip. Persisted in state so a redeploy doesn't accidentally
# resume discounts the owner wanted off.
_discount_paused_until = 0

# Per-unit discount skip: {listing_id (int) -> unix-timestamp until which discounts skip
# for this specific unit only}. Lets the owner say "hold price on this apartment" without
# pausing all discounts globally. Persisted.
_unit_discount_skip = {}

def is_unit_skipped(lid):
    try:
        ts = _unit_discount_skip.get(int(lid), 0)
        return float(ts) > time.time()
    except Exception:
        return False

def unit_skip_until_iso(lid):
    try:
        ts = _unit_discount_skip.get(int(lid), 0)
        if float(ts) <= time.time():
            return ""
        return datetime.fromtimestamp(float(ts), TZ).isoformat(timespec="minutes")
    except Exception:
        return ""

def is_discount_paused():
    return _discount_paused_until > time.time()

def discount_pause_status():
    """{paused, until_ts, until_iso}"""
    if not is_discount_paused():
        return {"paused": False, "until_ts": 0, "until_iso": ""}
    return {"paused": True, "until_ts": _discount_paused_until,
            "until_iso": datetime.fromtimestamp(_discount_paused_until, TZ).isoformat(timespec="minutes")}

async def _run_tier(pct, label):
    if is_discount_paused():
        print(f"[{label}] skipped — discounts paused by owner until "
              f"{datetime.fromtimestamp(_discount_paused_until, TZ).strftime('%a %H:%M')}")
        return
    try:
        changes, today = await asyncio.to_thread(apply_discount_tier, pct)
        mode = "DRY-RUN" if DISCOUNT_DRY_RUN else "LIVE"
        print(f"[{label} {today}] {mode} {pct:.0f}%: {len(changes)} empty units")
        for c in changes:
            print(f"   {c['name']}: orig {c['orig']} -> {c['new']}")
        await post_discount_summary(changes, today, pct, label)
    except Exception as e:
        print(f"{label} error:", e)

@tasks.loop(time=dt_time(hour=DISCOUNT_TIER1_HOUR, tzinfo=TZ))
async def discount_tier1_loop():
    if is_weekend_today():
        print("[Tier 1] Thu/Fri — skipping midnight discount (weekend rule)")
        return
    await _run_tier(DISCOUNT_TIER1_PERCENT, "Tier 1 (midnight)")

@tasks.loop(time=dt_time(hour=DISCOUNT_TIER2_HOUR, tzinfo=TZ))
async def discount_tier2_loop():
    if is_weekend_today():
        print("[Tier 2] Thu/Fri — skipping noon discount (weekend rule)")
        return
    await _run_tier(DISCOUNT_TIER2_PERCENT, "Tier 2 (noon)")

@tasks.loop(time=dt_time(hour=DISCOUNT_TIER3_HOUR, tzinfo=TZ))
async def discount_tier3_loop():
    if is_weekend_today():
        print("[Tier 3] Thu/Fri — skipping evening discount (weekend rule)")
        return
    await _run_tier(DISCOUNT_TIER3_PERCENT, "Tier 3 (6 PM)")

@tasks.loop(time=dt_time(hour=WEEKEND_DISCOUNT_HOUR, minute=WEEKEND_DISCOUNT_MINUTE, tzinfo=TZ))
async def discount_weekend_loop():
    if not is_weekend_today():
        return                       # only fires on Thu/Fri
    await _run_tier(WEEKEND_DISCOUNT_PERCENT, "Weekend (Thu/Fri 5:30 PM)")

def _headsup_table(items, weekend):
    """Build a clean monospace table + an explanatory note for the heads-up preview."""
    if weekend:
        wp = int(WEEKEND_DISCOUNT_PERCENT)
        c1, c2 = f"-{wp}%", "SAVE"
        header = f"{'UNIT':<16}{'NOW':>6}{c1:>6}{c2:>6}"
        rows = [f"{_clip(it['name'], 16):<16}{it['price']:>6}{it['w']:>6}"
                f"{it['price'] - it['w']:>6}" for it in items]
        note = f"Single drop if still empty: **-{wp}% at 5:30 PM** (weekend rule)."
    else:
        p1, p2, p3 = (int(DISCOUNT_TIER1_PERCENT), int(DISCOUNT_TIER2_PERCENT),
                      int(DISCOUNT_TIER3_PERCENT))
        c1, c2, c3 = f"-{p1}%", f"-{p2}%", f"-{p3}%"
        header = f"{'UNIT':<16}{'NOW':>6}{c1:>6}{c2:>6}{c3:>6}"
        rows = [f"{_clip(it['name'], 16):<16}{it['price']:>6}{it['t1']:>6}"
                f"{it['t2']:>6}{it['t3']:>6}" for it in items]
        note = (f"Prices auto-drop if still empty: **-{p1}% at {_fmt_hour(DISCOUNT_TIER1_HOUR)}** → "
                f"**-{p2}% at {_fmt_hour(DISCOUNT_TIER2_HOUR)}** → "
                f"**-{p3}% at {_fmt_hour(DISCOUNT_TIER3_HOUR)}**.")
    sep = "─" * len(header)
    # Prefix each line with a zero-width LEFT-TO-RIGHT MARK so an Arabic unit
    # name can't flip the line's direction and scramble the number columns.
    lines = [header, sep, *rows]
    return note, "\n".join("\u200e" + ln for ln in lines)

async def post_headsup(items, tomorrow, weekend):
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return
    category = await get_category(guild)
    channel = await ensure_channel(guild, HEADS_UP_CHANNEL, category)
    if channel is None:
        return
    try:
        date_str = datetime.strptime(tomorrow, "%Y-%m-%d").strftime("%a · %d %b %Y")
    except ValueError:
        date_str = tomorrow
    if not items:
        await channel.send(embed=discord.Embed(
            title="📋 Tomorrow's Open Units",
            description=f"**{date_str}**\n\nAll units are booked for tomorrow — nothing to discount. 🎉",
            color=GOLD))
        return
    shown = items[:45]
    extra = len(items) - len(shown)
    note, table = _headsup_table(shown, weekend)
    desc = f"**{date_str}** · **{len(items)} units** still open\n{note}\n```\n{table}\n```"
    if extra > 0:
        desc += f"\n*+{extra} more not shown.*"
    embed = discord.Embed(title="📋 Tomorrow's Open Units", description=desc, color=GOLD)
    embed.set_footer(text="All prices in SAR · preview only — nothing changes until the scheduled time.")
    await channel.send(embed=embed)

@tasks.loop(time=dt_time(hour=HEADS_UP_HOUR, tzinfo=TZ))
async def headsup_loop():
    try:
        items, tomorrow, weekend = await asyncio.to_thread(compute_headsup)
        print(f"[heads-up {tomorrow}] {len(items)} units open for tomorrow "
              f"({'weekend' if weekend else 'weekday'})")
        await post_headsup(items, tomorrow, weekend)
    except Exception as e:
        print("headsup error:", e)

# ====================== AI guest-message assistant ======================
# Claude drafts a reply, a human approves it in Discord, and only then is it sent.
ASSISTANT_RULES = """You are "فيصل", the front-desk assistant for Ouja Residence, a premium short-term \
rental company in Riyadh, Saudi Arabia. You draft replies to guest messages. A human teammate reviews \
every draft before it is sent, so be helpful but stay strictly within your lane.

TONE
- Warm, friendly, professional — Ritz-Carlton hospitality standard.
- Reply in the SAME language the guest used, switching immediately if they switch.
- For Arabic: write CLEAN, modern, natural Saudi Arabic with only a LIGHT local touch — \
warm phrases like "حياك الله"، "تم"، "أبشر"، "بالتوفيق" used naturally and sparingly. \
Do NOT write heavy or folksy Najdi slang. Aim for how a polished, well-spoken Saudi host \
talks — simple, elegant, respectful — not exaggerated dialect.
- Keep replies short, human, and to the point. Never reveal you are an AI unless asked.

CHOOSE ONE OF THREE ACTIONS
- "auto" → a VERY simple, safe, low-risk reply you are highly confident about, where a wrong \
answer would do no harm: greetings, thanks, reassurance, simple confirmations, and basic facts \
that are obvious or that you were explicitly given (e.g. a friendly "حياك الله", "شكراً لك", \
"تم، بالتوفiق"). These get sent to the guest automatically, so only use "auto" when you are sure.
- "reply" → a helpful reply you CAN draft, but a human should approve it first because it is more \
substantive, or you are not fully certain (most amenity/directions/check-in answers fall here).
- "escalate" → matches the MUST-escalate list below. Draft no reply.

WHEN IN DOUBT between "auto" and "reply", pick "reply" — a human approves it before it sends, so it is \
always safe. Only choose "escalate" when the request matches the MUST-escalate list (complaint, dispute, \
refund, booking change, upset guest, security info). A question you simply don't have the answer to \
(like live availability) is NOT a reason to escalate — suggest what you can and point the guest to the \
Airbnb link. Never gamble on "auto".

YOU MAY draft replies (auto or reply) about
- Unit amenities (wifi, parking, pool, kitchen, facilities)
- Check-in / check-out TIMES and the self-entry PROCESS (never the actual code)
- Directions, location, nearby restaurants and areas
- House-rules clarifications
- Greetings, thanks, general hospitality

ARRIVAL GUIDE LINK (important)
- When a guest asks about the location, the address, directions, where to park, the outer/building \
door number, or any arrival detail, point them to the unit's arrival-guide link (it is provided to \
you in the context as "Arrival-guide link for this unit"). Tell them all the details are there.
- Always include the exact link given to you. NEVER invent a link.
- If the link is "NOT AVAILABLE", do NOT make one up — set action to "escalate" instead.
- If the guest says they can't open it or nothing happens, explain it opens an Airbnb warning page \
("you're leaving Airbnb"): they should tap "متابعة" (or "Continue" if their app is in English), \
then tap the guide/directions option. (This is "auto"/"reply" — just a helpful instruction.)

PRE-BOOKING PRIVACY (critical)
- The context gives you "Booking status". If it is NOT CONFIRMED (an inquiry or pre-booking), you \
MUST NOT share the exact location, address, building/door number, or the arrival-guide link — even \
if the guest asks directly. Politely tell them the full location and arrival details are sent right \
after the booking is confirmed. You may still talk about the general area, amenities, and price.
- Only share location and the arrival-guide link when Booking status is CONFIRMED.

SUGGESTING A UNIT / AVAILABILITY  (do NOT escalate these — suggest instead)
- If the guest asks for another/different unit, a bigger/cheaper/smaller one, a unit in another area, \
a unit with a certain feature (balcony, pool, terrace, X bedrooms, etc.), OR simply "do you have a \
unit available today / for these dates?": this is a SUGGESTION task. Use action "reply" (a human \
approves it). It is NOT an escalation.
- FIRST, if you don't already know what they want, ask briefly: preferred area, number of bedrooms, \
and any must-have or budget. If they already told you, skip the questions and suggest right away.
- Then, from the "قائمة وحدات عوجا" in the context, suggest 1-3 matches. For each: name, bedrooms, \
area, the "starting from" nightly price, and the Airbnb link if it is in the list. NEVER invent a link \
or a detail. If nothing matches exactly, suggest the closest and state the differences honestly.
- AVAILABILITY: you do NOT have live availability. Never promise a unit is free. Instead, suggest the \
options and tell the guest to check live availability and book directly from the Airbnb link (the link \
always shows what is open for their dates). Not knowing availability is NEVER a reason to escalate — \
suggest + send them to the link.
- A FEATURE you're not sure about (e.g. whether a unit allows smoking, or has a specific view): if it \
is not in your provided info, suggest the closest units, be honest that you'd confirm that specific \
detail with the team, and keep it action "reply" so a human checks. Do NOT invent the feature.
- Whenever you mention a price, add a short note that prices are approximate and BEFORE tax and the \
platform service fee.
- MIXED message: if a guest asks several things and you can help with some (suggest units, directions, \
amenities) but one part truly needs a human (e.g. extending checkout, a refund), DRAFT a "reply" that \
handles what you can and says you'll check the rest with the team — do not escalate the whole message.

OPTIONAL EXTRAS / UPSELLS (offer gently — never push, never auto-promise)
- You may mention Ouja's optional paid extras when it naturally fits and would genuinely help the guest, \
phrased as a friendly offer, not a hard sell. Good moments: a guest arriving early or asking about \
arrival time → early check-in; a guest asking about checkout or a late flight → late checkout; a guest \
asking about airport pickup or transport → the Sawari Al Musafir chauffeur service; a long stay → an \
extra mid-stay cleaning.
- These are subject to availability and a fee, so you CANNOT confirm them yourself. Offer it, say the \
team will confirm availability and the price, and set action to "reply" (a human approves). Never promise \
a time or a price you weren't given, and never invent a fee. One soft offer is enough — don't repeat it.
- If the guest says no or ignores it, drop it immediately and don't bring it up again.

YOU MUST NOT do these — instead set action to "escalate"
- Confirm, modify, cancel, or refund a booking
- Offer any discount, comp, or price change
- Share the door/entry CODE or any building security info
- Share other guests', owners', or internal/financial information
- Handle any complaint, dispute, damage claim, or an upset guest
- Promise late checkout, early check-in, or extra services you cannot verify
- Give legal, medical, or financial advice
- Discuss anything outside hosting / off-topic
- State any fact about the unit you were not given — never invent details
- Anything you are unsure about — when in doubt, escalate; never guess

OUTPUT — respond with ONLY a JSON object, nothing else:
{"action": "auto" | "reply" | "escalate",
 "reply": "the drafted message to the guest IN THE GUEST'S OWN LANGUAGE; empty string if escalating",
 "intent": "short label IN ARABIC, e.g. واي فاي، اتجاهات، تسجيل دخول، تسعير، شكوى، تعديل حجز",
 "sentiment": "ok" | "upset",
 "reason": "one short line IN ARABIC for the human reviewer explaining your choice (the team reads Arabic)",
 "confidence": 0.0-1.0}

IMPORTANT: "reply" stays in the guest's language (Najdi Arabic if they wrote Arabic). But "intent" and \
"reason" must ALWAYS be written in Arabic, because the Ouja team reading these cards speaks Arabic."""

def _msg_is_inbound(m):
    return int(m.get("isIncoming", m.get("incoming", 0)) or 0) == 1

def _msg_time(m):
    return str(m.get("date") or m.get("insertedOn") or m.get("latestMessageDate") or "")

def _msg_sort_key(m):
    """Sortable timestamp so the guest's *latest* message is reliably the newest.
    (Within one conversation the tz skew is uniform, so relative order stays correct.)"""
    return _parse_msg_dt(_msg_time(m)) or datetime.min.replace(tzinfo=TZ)

def _parse_msg_dt(s):
    """Parse a Hostaway message timestamp as Riyadh local time. Returns aware dt or None.
    Parsing as TZ is safe for baselining: a tz mismatch can only make a message look OLDER
    (so it gets baselined like before), never wrongly resurrect an old one."""
    s = str(s).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s[:19], fmt).replace(tzinfo=TZ)
        except Exception:
            pass
    return None

def _looks_automated(body):
    """True if an outbound message looks like an automated welcome/booking message
    (i.e. not a real answer to the guest)."""
    b = (body or "").lower()
    return any(mk.lower() in b for mk in AUTO_REPLY_MARKERS)

_guide_cache = {}

def get_guide_url(listing_id):
    """Pull the arrival-guide link stored in the listing's Custom Fields. Cached per listing."""
    if listing_id in _guide_cache:
        return _guide_cache[listing_id]
    url = None
    try:
        data = api_get(f"/listings/{listing_id}", params={"includeResources": 1})
        listing = data.get("result") or {}
        # 1) look through the listing's custom-field values for a URL
        for key in ("listingCustomFieldValues", "customFieldValues", "customFields"):
            for cf in (listing.get(key) or []):
                v = str(cf.get("value") or "").strip()
                if v.startswith("http"):
                    url = v
                    break
            if url:
                break
        # 2) fallback: scan the whole listing for the guide domain
        if not url:
            blob = json.dumps(listing, ensure_ascii=False)
            m = (re.search(r"https?://[^\s\"']*oujaguide[^\s\"']*", blob)
                 or re.search(r"https?://[^\s\"']*netlify[^\s\"']*", blob))
            if m:
                url = m.group(0)
    except Exception as e:
        print(f"guide url error for listing {listing_id}: {e}")
    _guide_cache[listing_id] = url
    return url

# A booking only counts as "confirmed" (safe to share location/guide) for these statuses.
CONFIRMED_STATUSES = {"new", "modified"}

def get_reservation_status(reservation_id):
    """Return the reservation status (lowercased), or '' if unknown. Not cached — it can change."""
    if not reservation_id:
        return ""
    try:
        data = api_get(f"/reservations/{reservation_id}")
        return (data.get("result", {}) or {}).get("status", "").lower()
    except Exception as e:
        print(f"reservation status error ({reservation_id}):", e)
        return ""

# Knowledge base loaded from the #knowledge Discord channel; injected into every draft.
_knowledge_text = ""

# Units catalog (name · bedrooms · area · base price · Airbnb link) pulled from Hostaway.
_catalog_text = ""
_catalog_ts = 0
_catalog_units = []        # structured: [{id, name, beds, area, price, link}]
# availability/price cache: (listing_id, checkin, checkout) -> (result|None, ts)
# Bounded so a busy day can't grow this forever (each unique date range is one entry).
_avail_cache = OrderedDict()
_AVAIL_CACHE_MAX = 2000
INTEL_CACHE_MIN  = int(os.environ.get("INTEL_CACHE_MIN", "20"))    # cache calendar lookups
INTEL_MAX_CHECKS = int(os.environ.get("INTEL_MAX_CHECKS", "14"))   # max units to date-check per msg

def _listing_active(L):
    """False if the listing looks inactive/unlisted (the red 🚫 in Hostaway) — skip those."""
    v = L.get("status")
    if isinstance(v, str) and v.lower() in (
            "inactive", "disabled", "unlisted", "delisted", "deleted", "draft", "paused", "off"):
        return False
    if v in (0, "0", False):
        return False
    for key in ("isActive", "listed", "active", "isListed"):
        if key in L and L.get(key) in (0, "0", False, "false", "False"):
            return False
    return True

def _airbnb_link(L):
    """Best-effort Airbnb listing URL from the listing's channel data."""
    blob = json.dumps(L, ensure_ascii=False)
    m = (re.search(r"https?://[^\s\"']*airbnb\.[^\s\"']*/rooms/\d+", blob)
         or re.search(r"https?://[^\s\"']*airbnb\.[^\s\"']*", blob))
    if m:
        return m.group(0)
    m2 = re.search(r'"airbnb[A-Za-z]*[Ii]d"\s*:\s*"?(\d{5,})"?', blob)
    if m2:
        return f"https://www.airbnb.com/rooms/{m2.group(1)}"
    return ""

def _nightly_from(listing_id):
    """A representative 'starting from' nightly price from the calendar (next ~30 days)."""
    try:
        today = datetime.now(TZ).date()
        data = api_get(f"/listings/{listing_id}/calendar",
                       params={"startDate": today.isoformat(),
                               "endDate": (today + timedelta(days=30)).isoformat()})
        prices = [d.get("price") for d in (data.get("result", []) or [])
                  if d.get("isAvailable", 1) and isinstance(d.get("price"), (int, float))
                  and d.get("price") > 0]
        return min(prices) if prices else None
    except Exception as e:
        print(f"price fetch error ({listing_id}):", e)
        return None

def load_catalog(force=False):
    """Build a units catalog from Hostaway listings (cached 1h). Used to suggest alternatives.
    Skips inactive/unlisted listings (the red 🚫)."""
    global _catalog_text, _catalog_ts, _catalog_units
    if not force and _catalog_text and (time.time() - _catalog_ts) < 3600:
        return
    try:
        data = api_get("/listings", params={"limit": 100, "includeResources": 1})
        rows, units, skipped = [], [], 0
        for L in (data.get("result", []) or []):
            name = (L.get("internalListingName") or L.get("name") or "").strip()
            if not name:
                continue
            if not _listing_active(L):
                skipped += 1
                if CATALOG_DEBUG:
                    print(f"  catalog SKIP (inactive): {name} · status={L.get('status')!r}")
                continue
            beds = L.get("bedroomsNumber")
            area = (L.get("city") or L.get("address") or "").strip()
            price = (_nightly_from(L.get("id")) if CATALOG_CALENDAR_PRICES else None) or L.get("price")
            link = _airbnb_link(L)
            parts = [name]
            if beds:
                parts.append(f"{beds} غرفة نوم")
            if area:
                parts.append(area)
            if price:
                parts.append(f"تبدأ من ~{round(price)} ر.س/الليلة")
            if link:
                parts.append(link)
            rows.append(" · ".join(parts))
            units.append({"id": L.get("id"), "name": name, "beds": beds, "area": area,
                          "price": round(price) if price else None, "link": link})
            if CATALOG_DEBUG:
                print(f"  catalog OK: {name} · status={L.get('status')!r} · link={'yes' if link else 'no'}")
        _catalog_text = "\n".join(rows)[:6000]
        _catalog_units = units
        _catalog_ts = time.time()
        print(f"catalog: loaded {len(rows)} active units (skipped {skipped} inactive)")
    except Exception as e:
        print("catalog load error:", e)

def _parse_date(s):
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except Exception:
        return None

def unit_availability_price(listing_id, checkin, checkout):
    """Check the calendar for ONE unit over a specific stay. Returns
    {available, nights, total, avg} (total/avg before tax & platform fee) or None
    if unknown. Cached for INTEL_CACHE_MIN minutes."""
    if not listing_id or not checkin or not checkout:
        return None
    ci, co = _parse_date(checkin), _parse_date(checkout)
    if not ci or not co or co <= ci:
        return None
    key = (listing_id, ci.isoformat(), co.isoformat())
    hit = _avail_cache.get(key)
    if hit and (time.time() - hit[1]) < INTEL_CACHE_MIN * 60:
        return hit[0]
    last_night = co - timedelta(days=1)          # checkout night is not charged
    nights = (co - ci).days
    result = None
    try:
        data = api_get(f"/listings/{listing_id}/calendar",
                       params={"startDate": ci.isoformat(), "endDate": last_night.isoformat()})
        days = data.get("result", []) or []
        if days:
            available = all(int(d.get("isAvailable", 0) or 0) == 1 for d in days)
            prices = [d.get("price") for d in days
                      if isinstance(d.get("price"), (int, float)) and d.get("price") > 0]
            total = round(sum(prices)) if len(prices) == len(days) and prices else None
            avg = round(total / nights) if total else None
            result = {"available": available, "nights": nights, "total": total, "avg": avg}
    except Exception as e:
        print(f"availability fetch error ({listing_id}):", e)
        result = None
    _bounded_cache_put(_avail_cache, key, (result, time.time()), _AVAIL_CACHE_MAX)
    return result

def enrich_catalog_for_dates(checkin, checkout, exclude_id=None):
    """Build a catalog block that marks live availability + real total for the guest's
    dates. Caps how many units we date-check (INTEL_MAX_CHECKS) to stay light. Units
    beyond the cap (or with unknown calendars) just show the 'starting from' price."""
    if not _catalog_units or not checkin or not checkout:
        return _catalog_text
    lines, checked = [], 0
    for u in _catalog_units:
        base = [u["name"]]
        if u.get("beds"):
            base.append(f"{u['beds']} غرفة نوم")
        if u.get("area"):
            base.append(u["area"])
        info = None
        if checked < INTEL_MAX_CHECKS and u.get("id") and u["id"] != exclude_id:
            info = unit_availability_price(u["id"], checkin, checkout)
            checked += 1
        if info and info.get("total") is not None:
            tag = "✅ متاحة لتواريخه" if info["available"] else "❌ غير متاحة لتواريخه"
            base.append(f"{tag} · {info['nights']} ليالي ≈ {info['total']} ر.س (متوسط {info['avg']}/ليلة)")
        elif info and info.get("available") is True:
            base.append("✅ متاحة لتواريخه")
        elif info and info.get("available") is False:
            base.append("❌ غير متاحة لتواريخه")
        elif u.get("price"):
            base.append(f"تبدأ من ~{u['price']} ر.س/الليلة")
        if u.get("link"):
            base.append(u["link"])
        lines.append(" · ".join(base))
    return "\n".join(lines)[:6500]

# Hints that the guest is asking about a different unit, availability, or a feature
# (any of these injects the units catalog so the bot SUGGESTS instead of escalating).
_ALT_HINTS = [
    # another / different / bigger / cheaper
    "ثاني", "ثانيه", "ثانية", "بديل", "غيره", "غيرها", "اكبر", "أكبر", "ارخص", "أرخص",
    "اصغر", "أصغر", "خيار", "خيارات", "وحده ثاني", "شقه ثاني",
    "another", "other", "different", "bigger", "cheaper", "smaller", "option", "alternativ",
    # availability / is there a unit
    "متاح", "متاحه", "متاحة", "متوفر", "متوفره", "متوفرة", "توفر", "التوفر", "فاضي", "فاضيه",
    "فاضية", "شاغر", "شاغره", "فيه وحده", "فيه شقة", "فيه شقه", "عندكم وحده", "عندكم شقة",
    "available", "availab", "vacant", "vacancy", "any unit", "do you have a unit",
    # features that point to a different unit
    "بلكون", "تراس", "مسبح", "تدخين", "حوش", "استوديو", "غرفتين", "ثلاث غرف", "ثلاث غرفه",
    "balcony", "terrace", "pool", "smoking", "studio", "two bedroom", "2 bedroom",
    "three bedroom", "3 bedroom",
]

# Hints that the guest is asking about price / total cost (to compute their real total).
_PRICE_HINTS = ["سعر", "السعر", "كم", "بكم", "كام", "تكلفة", "التكلفة", "المبلغ", "اجمالي", "الاجمالي",
                "الإجمالي", "price", "cost", "how much", "total", "rate", "nightly"]

def claude_draft(guest_name, unit, history_text, guide_url=None, confirmed=False,
                 dates=None, listing_id=None):
    """Call Claude to draft a reply. Returns parsed dict or None on failure."""
    if not ANTHROPIC_API_KEY:
        print("assistant: ANTHROPIC_API_KEY not set")
        return None
    low = history_text.lower()
    status_line = ("Booking status: CONFIRMED" if confirmed
                   else "Booking status: NOT CONFIRMED (inquiry / pre-booking)")
    guide_line = (f"Arrival-guide link for this unit: {guide_url}"
                  if (guide_url and confirmed)
                  else "Arrival-guide link for this unit: NOT AVAILABLE / do not share")
    dates_line = (f"\nتواريخ الحجز: {dates[0]} إلى {dates[1]}"
                  if dates and dates[0] else "")
    facts = _knowledge_text.strip()
    facts_block = (f"معلومات معتمدة عن عوجا (استخدمها كمصدر الحقيقة وصحّح أي تعارض):\n{facts}\n\n"
                   if facts else "")
    want_catalog = bool(_catalog_text) and any(h in low for h in _ALT_HINTS)
    # ---- real pricing for the guest's OWN unit (when dates known + a price/availability question) ----
    own_price_line = ""
    if (dates and dates[0] and listing_id
            and (want_catalog or any(h in low for h in _PRICE_HINTS))):
        info = unit_availability_price(listing_id, dates[0], dates[1])
        if info and info.get("total") is not None:
            avail = "متاحة" if info["available"] else "غير متاحة حالياً"
            own_price_line = (
                f"\nالتسعير الفعلي لوحدة الضيف ({unit}) لتواريخه (قبل الضريبة ورسوم المنصة): "
                f"{info['nights']} ليالي ≈ {info['total']} ر.س (متوسط {info['avg']}/ليلة) · الوحدة {avail}.")
        elif info and info.get("available") is not None:
            own_price_line = (f"\nوحدة الضيف ({unit}) "
                              f"{'متاحة' if info['available'] else 'غير متاحة'} لتواريخه.")
    # ---- alternatives: use a live-availability catalog when we know the dates ----
    if want_catalog and dates and dates[0]:
        catalog_data = enrich_catalog_for_dates(dates[0], dates[1], exclude_id=listing_id)
        avail_note = ("- التواريخ معروفة، فالقائمة تبيّن التوفّر الفعلي ✅/❌ والإجمالي الحقيقي لتواريخه. "
                      "اقترح فقط الوحدات المعلّمة ✅ متاحة، واذكر الإجمالي المبيّن. لا تقترح وحدة ❌.\n")
    else:
        catalog_data = _catalog_text
        avail_note = ("- إنت ما تعرف التوفّر المباشر لتواريخه — اعرض الخيارات ووجّهه يتأكد ويحجز من رابط "
                      "Airbnb. **السؤال عن التوفّر مو سبب للتصعيد إطلاقاً**.\n")
    catalog_block = (
        "قائمة وحدات عوجا للاقتراح عند طلب بديل أو سؤال عن التوفّر:\n" + catalog_data + "\n\n"
        "تعليمات الاقتراح:\n"
        "- أول ما يطلب شقة/وحدة ثانية أو بديل أو يسأل (فيه وحده متاحه؟ / عندكم شي فاضي؟): اسأله بلطف "
        "عن اللي يبيه (أي حي، كم غرفة، وش المهم له) إلا إذا قالها، وبعدها اقترح طول.\n"
        "- طابق من القائمة واقترح 1-3 خيارات. لكل خيار: الاسم، عدد الغرف، المنطقة، السعر، ورابط Airbnb "
        "لو موجود. لا تخترع رابط أو تفاصيل.\n"
        "- لو ما فيه مطابق تماماً، اقترح أقرب خيار ووضّح الفروقات بصراحة.\n"
        + avail_note +
        "- ميزة مو متأكد منها (تدخين؟ بلكون؟) وما هي عندك بالمعلومات: اقترح أقرب الوحدات، وقل بصراحة "
        "إنك بتتأكد من هالتفصيلة مع الفريق، وخلها رد (يراجعه إنسان). لا تخترع.\n"
        "- إذا ذكرت سعر، أضف تنويه: الأسعار تقريبية وقبل الضريبة ورسوم المنصة.\n\n"
        ) if want_catalog else ""
    user = (f"{facts_block}{catalog_block}Guest name: {guest_name}\nUnit: {unit}\n"
            f"{status_line}\n{guide_line}{dates_line}{own_price_line}\n\n"
            f"Conversation so far (oldest first, last line is the guest's new message):\n"
            f"{history_text}\n\nDraft your reply as the JSON object.")
    model = CLAUDE_MODEL_PREMIUM if want_catalog else CLAUDE_MODEL
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": model, "max_tokens": 700, "system": ASSISTANT_RULES,
                  "messages": [{"role": "user", "content": user}]},
            timeout=60,
        )
        r.raise_for_status()
        blocks = r.json().get("content", []) or []
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
        text = text.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # The model sometimes wraps the JSON in a sentence ("Here's the reply: {...}").
            # Pull out the first balanced {...} block and try again instead of dropping the
            # draft entirely.
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    pass
            print("claude_draft: could not parse JSON · raw=", text[:300])
            return None
    except Exception as e:
        print("claude_draft error:", e)
        return None

def claude_text(system, user, max_tokens=600, model=None):
    """Plain-text Claude call (no JSON). Returns the text or None."""
    if not ANTHROPIC_API_KEY:
        return None
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": model or CLAUDE_MODEL, "max_tokens": max_tokens, "system": system,
                  "messages": [{"role": "user", "content": user}]},
            timeout=60,
        )
        r.raise_for_status()
        blocks = r.json().get("content", []) or []
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip() or None
    except Exception as e:
        print("claude_text error:", e)
        return None

def claude_escalation_ack(guest, unit, history, guest_text):
    """An empathetic, problem-specific holding message for a repeat escalation."""
    sys = ("أنت تكتب رسالة طمأنة قصيرة لضيف في عوجا تصعّد موضوعه مرة ثانية وهو لا يزال ينتظر أو منزعج. "
           "اكتب بأسلوب سعودي نجدي دافئ وراقٍ: اعترف بمشكلته تحديداً، تفهّم شعوره، اعتذر بصدق، "
           "وطمّنه إن الفريق المختص يشتغل على موضوعه الحين وبيتواصل معه قريب جداً. "
           "لا تكتبها كأنها قالب آلي مكرر. لو الضيف يكتب إنجليزي رد بالإنجليزي. اكتب نص الرسالة فقط.")
    user = (f"الوحدة: {unit}\nالضيف: {guest}\nالمحادثة:\n{history}\n\n"
            f"آخر رسالة من الضيف: {guest_text}")
    return claude_text(sys, user, 500, model=CLAUDE_MODEL_PREMIUM) or claude_text(sys, user, 500)

def claude_manager_script(guest, unit, history, guest_text, reason, manager_name):
    """A ready-to-send reply in the owner's warm/charismatic voice for whoever claims."""
    sys = (f"أنت تكتب رسالة جاهزة بينسخها {manager_name} (مدير العقار في عوجا) ويرسلها للضيف مباشرة. "
           "الأسلوب: سعودي نجدي دافئ، واثق، وكاريزما عالية مثل صاحب البيت اللي يهتم بضيفه شخصياً. "
           f"الرسالة لازم: تحيي الضيف بحرارة، تعرّف إن {manager_name} مدير العقار وتولّى الموضوع بنفسه، "
           "تذكر إن الشباب (الفريق) بلّغوه عن مشكلته، تلخّص مشكلته باختصار عشان يحس إنه مسموع، "
           "تتفهّم وتعتذر بصدق، وتطمّنه بعبارات دافئة (مثل: أبشر بالي يسرّ خاطرك يا طويل العمر) إن الموضوع بينحل. "
           "طبيعية مهب قالب جامد. لو الضيف يكتب إنجليزي رد بالإنجليزي. اكتب نص الرسالة فقط بدون أي شرح.")
    user = (f"الوحدة: {unit}\nالضيف: {guest}\nسبب التصعيد: {reason}\nالمحادثة:\n{history}\n\n"
            f"آخر رسالة من الضيف: {guest_text}")
    return claude_text(sys, user, 700, model=CLAUDE_MODEL_PREMIUM) or claude_text(sys, user, 700)

def _conv_to_item(c, listings, seen, debug=False):
    """Turn ONE conversation object into a new-guest-message item, or None.
    Shared by the full scan and the single-conversation webhook path."""
    cid = c.get("id")
    if not cid:
        return None
    try:
        md = api_get(f"/conversations/{cid}/messages")
        msgs = md.get("result", []) or []
    except Exception as e:
        if debug:
            print(f"  conv {cid}: messages fetch error: {e}")
        return None
    if not msgs:
        return None
    msgs = sorted(msgs, key=_msg_sort_key)
    # the guest's most recent (inbound) message
    guest_idx = next((i for i in range(len(msgs) - 1, -1, -1)
                      if _msg_is_inbound(msgs[i])), None)
    if guest_idx is None:
        return None                                     # guest never messaged
    guest_msg = msgs[guest_idx]
    mid = str(guest_msg.get("id"))
    after = msgs[guest_idx + 1:]                         # anything sent after the guest spoke
    # "answered" = a real reply exists after the guest (not just an automated welcome)
    answered = bool(after) and not all(
        _looks_automated(m.get("body") or "") for m in after)
    if debug:
        print(f"  conv {cid}: {len(msgs)} msgs · guest_last_id={mid} · after={len(after)} · "
              f"answered={answered} · body={(guest_msg.get('body') or '')[:50]!r}")
    if mid in seen:
        return None                                     # already drafted for this message
    if not ASSISTANT_ALWAYS_DRAFT:
        if answered:
            return None                                 # a real human/bot reply already exists
        if after and not ASSISTANT_ANSWER_PAST_AUTO:
            return None                                 # only auto-replies after, feature off
    lm = c.get("listingMapId")
    unit = listings.get(lm) or c.get("listingName") or f"unit-{lm}"
    guest = c.get("recipientName") or c.get("guestName") or "Guest"
    res = c.get("reservation") or {}
    history = "\n".join(
        f"{'Guest' if _msg_is_inbound(m) else 'Host'}: {(m.get('body') or '').strip()}"
        for m in msgs[-8:] if (m.get("body") or "").strip())
    return {
        "conversation_id": cid, "message_id": mid, "guest": guest, "unit": unit,
        "listing_id": lm,
        "reservation_id": c.get("reservationId") or res.get("id"),
        "res_status": (res.get("status") or "").lower(),
        "comm_type": guest_msg.get("communicationType") or "email",
        "guest_text": (guest_msg.get("body") or "").strip(), "history": history,
        "last_time": _msg_time(guest_msg),
        "checkin": res.get("arrivalDate"), "checkout": res.get("departureDate"),
    }

def fetch_new_guest_messages(seen, debug=False):
    """Scan recent conversations, fetch each one's messages, and return new inbound
    guest messages (the guest's latest message that hasn't been answered/seen)."""
    listings = get_listings_map()
    out = []
    try:
        data = api_get("/conversations", params={"limit": ASSISTANT_SCAN, "includeResources": 1})
    except Exception as e:
        print("assistant fetch error:", e)
        return out
    convos = data.get("result", []) or []
    if debug:
        print(f"assistant DEBUG: /conversations returned {len(convos)} conversations")
    for c in convos:
        it = _conv_to_item(c, listings, seen, debug)
        if it:
            out.append(it)
    if debug:
        print(f"assistant DEBUG: {len(out)} new inbound guest message(s) to draft")
    return out

def fetch_conversation_item(conversation_id, seen):
    """Fetch ONE conversation (for the webhook path) and return its new-message item or None."""
    listings = get_listings_map()
    try:
        data = api_get(f"/conversations/{conversation_id}", params={"includeResources": 1})
    except Exception as e:
        print(f"webhook: conversation {conversation_id} fetch error:", e)
        return None
    c = data.get("result") or {}
    if not c:
        return None
    if not c.get("id"):
        c["id"] = conversation_id
    return _conv_to_item(c, listings, seen)

SIGNATURE_VARY = os.environ.get("SIGNATURE_VARY", "1") in ("1", "true", "True", "yes")

# 50 varied Najdi/warm sign-offs so no two messages end the same way.
SIGNATURES_AR = [
    "تحياتي،\nمساعد - فريق عوجا 🤍", "كامل التوفيق،\nأخوك مساعد - فريق عوجا",
    "في أمان الله،\nمساعد من عوجا 🤍", "تسلم،\nمساعد - عوجا",
    "أي خدمة ثانية أنا حاضر،\nمساعد - فريق عوجا 🤍", "سعدنا بخدمتك،\nمساعد من عوجا",
    "لا تتردد تطلبني،\nأخوك مساعد - عوجا 🤍", "نتشرف فيك دايم،\nفريق عوجا - مساعد",
    "حياك الله،\nمساعد - فريق عوجا 🤍", "بالخدمة دايماً،\nمساعد من عوجا",
    "تحياتي القلبية،\nمساعد - عوجا 🤍", "يومك سعيد،\nأخوك مساعد - فريق عوجا",
    "تواصل معي أي وقت،\nمساعد - عوجا 🤍", "شاكر لك،\nمساعد من فريق عوجا",
    "دمت بخير،\nمساعد - عوجا 🤍", "خدمتك شرف لنا،\nفريق عوجا",
    "أبشر بكل اللي يسعدك،\nمساعد - عوجا 🤍", "تقبل تحياتي،\nمساعد من عوجا",
    "نحن في خدمتك،\nفريق عوجا - مساعد 🤍", "الله يحييك،\nأخوك مساعد - عوجا",
    "أي استفسار ثاني أنا موجود،\nمساعد - فريق عوجا 🤍", "سرّنا تواصلك،\nمساعد من عوجا",
    "بالتوفيق،\nمساعد - عوجا 🤍", "تستاهل كل خير،\nفريق عوجا - مساعد",
    "حاضرين لك،\nمساعد - فريق عوجا 🤍", "تحياتي وتقديري،\nمساعد من عوجا",
    "نوّرتنا،\nمساعد - عوجا 🤍", "أمرك،\nأخوك مساعد - فريق عوجا",
    "خليك على تواصل،\nمساعد - عوجا 🤍", "سعيد بخدمتك،\nمساعد من فريق عوجا",
    "الله يسعدك،\nمساعد - عوجا 🤍", "تحت أمرك دايم،\nفريق عوجا - مساعد",
    "ودّي وتحياتي،\nمساعد من عوجا 🤍", "عساك على القوة،\nأخوك مساعد - عوجا",
    "أي شي تحتاجه أنا جاهز،\nمساعد - فريق عوجا 🤍", "شكراً لثقتك،\nمساعد من عوجا",
    "بكل سرور،\nمساعد - عوجا 🤍", "اعتبرني أخوك،\nمساعد - فريق عوجا",
    "دايم بالخدمة،\nمساعد من عوجا 🤍", "تحياتي الحارة،\nفريق عوجا - مساعد",
    "الله يوفقك،\nمساعد - عوجا 🤍", "نتمنى لك إقامة سعيدة،\nمساعد من فريق عوجا",
    "حياك في أي وقت،\nمساعد - عوجا 🤍", "تسلم وما تقصّر،\nأخوك مساعد - عوجا",
    "خدمتك أولوية عندنا،\nفريق عوجا 🤍", "بانتظار خدمتك،\nمساعد - عوجا",
    "مع خالص الود،\nمساعد من عوجا 🤍", "سعدنا فيك،\nمساعد - فريق عوجا",
    "كلنا بالخدمة،\nمساعد - عوجا 🤍", "الله يتمّم لك على خير،\nأخوك مساعد - فريق عوجا",
]
SIGNATURES_EN = [
    "Best regards,\nMusaid – Ouja Team 🤍", "At your service,\nMusaid – Ouja",
    "Always happy to help,\nMusaid – Ouja Team 🤍", "Warm regards,\nMusaid from Ouja",
    "Reach out anytime,\nMusaid – Ouja Team 🤍", "Take care,\nMusaid – Ouja",
    "Glad to assist,\nMusaid – Ouja Team 🤍", "Anything else, I'm here,\nMusaid – Ouja",
    "Wishing you a great stay,\nMusaid – Ouja Team 🤍", "Kind regards,\nMusaid from Ouja",
    "We're here for you,\nOuja Team – Musaid 🤍", "Thanks for reaching out,\nMusaid – Ouja",
    "All the best,\nMusaid – Ouja Team 🤍", "Happy to help anytime,\nMusaid – Ouja",
    "With pleasure,\nMusaid – Ouja Team 🤍", "Don't hesitate to ask,\nMusaid from Ouja",
    "Here whenever you need,\nMusaid – Ouja 🤍", "Cheers,\nMusaid – Ouja Team",
    "Your comfort is our priority,\nOuja Team 🤍", "Talk soon,\nMusaid – Ouja",
]

def _has_arabic(s):
    return any("\u0600" <= ch <= "\u06ff" for ch in str(s))

def _pick_signature(arabic):
    if not SIGNATURE_VARY:
        return ASSISTANT_SIGNATURE_AR if arabic else ASSISTANT_SIGNATURE_EN
    return random.choice(SIGNATURES_AR if arabic else SIGNATURES_EN)

def with_signature(text):
    """Append a (rotating) support signature, language-matched to the message."""
    return f"{str(text).rstrip()}\n\n{_pick_signature(_has_arabic(text))}"

def send_guest_message(conversation_id, body, comm_type="email"):
    return api_post(f"/conversations/{conversation_id}/messages",
                    {"body": with_signature(body), "communicationType": comm_type})

# pending escalations: discord_message_id -> {channel_id, guest, unit, last_ping, attempts, claimed_by}
_escalations = {}
_esc_ack_count = {}     # conversation_id -> how many escalation acks we've sent
_esc_sent_acks = {}     # conversation_id -> [ack bodies we sent] (to tell our msgs from a co-host's)
_claimed_convos = set() # conversation_ids a human has claimed (stop auto-acks)

class NameSelect(discord.ui.Select):
    """The name picker shown after tapping Claim."""
    def __init__(self, channel_id, message_id):
        super().__init__(placeholder="اختر اسمك للاستلام…", min_values=1, max_values=1,
                         options=[discord.SelectOption(label=n) for n in CLAIM_NAMES])
        self.target_channel_id = channel_id
        self.target_message_id = message_id

    async def callback(self, interaction: discord.Interaction):
        name = self.values[0]
        esc = _escalations.get(self.target_message_id)
        if esc and esc.get("claimed_by"):
            await interaction.response.edit_message(
                content=f"⚠️ التصعيد مستلم مسبقاً بواسطة {esc['claimed_by']}.", view=None)
            return
        if esc:
            esc["claimed_by"] = name
            if esc.get("conversation_id"):
                _claimed_convos.add(esc["conversation_id"])   # stop auto-acks
            log_event("escalation", f"تم استلام تصعيد بواسطة {name} · {esc.get('unit','')}")
        try:
            ch = interaction.client.get_channel(self.target_channel_id)
            msg = await ch.fetch_message(self.target_message_id)
            embed = msg.embeds[0] if msg.embeds else discord.Embed()
            embed.add_field(name="✅ تم الاستلام", value=f"بواسطة **{name}**", inline=False)
            embed.color = 0x3BA55D
            done = ClaimView()
            for c in done.children:
                c.disabled = True
            await msg.edit(embed=embed, view=done)
        except Exception as e:
            print("claim edit error:", e)
        tail = " — جهّزت لك رد جاهز تحت 👇" if (esc and MANAGER_SCRIPT) else ""
        await interaction.response.edit_message(
            content=f"✅ استلمت التصعيد باسم **{name}**.{tail}", view=None)
        # show the claimer a ready-to-send reply (private to them, right here in the channel)
        if esc and MANAGER_SCRIPT:
            script = await asyncio.to_thread(
                claude_manager_script, esc.get("guest"), esc.get("unit"),
                esc.get("history", ""), esc.get("guest_text", ""), esc.get("reason", ""), name)
            if script:
                dm = (f"🎯 رد جاهز للضيف **{esc.get('guest')} · {esc.get('unit')}** "
                      f"(انسخ والصق ثم أرسل):\n\n{script}")
            else:
                dm = ("⚠️ تعذّر توليد الرد الجاهز — تواصل مع الضيف مباشرة.")
            await interaction.followup.send(dm, ephemeral=True)

class ClaimView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)   # persistent across restarts

    @discord.ui.button(label="🙋 أخذ المهمة / Claim", style=discord.ButtonStyle.primary,
                       custom_id="ouja_claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        esc = _escalations.get(interaction.message.id)
        if esc and esc.get("claimed_by"):
            await interaction.response.send_message(
                f"⚠️ مستلم مسبقاً بواسطة {esc['claimed_by']}.", ephemeral=True)
            return
        picker = discord.ui.View(timeout=300)
        picker.add_item(NameSelect(interaction.channel.id, interaction.message.id))
        await interaction.response.send_message("اختر اسمك للاستلام:", view=picker, ephemeral=True)

class EditModal(discord.ui.Modal, title="تعديل الرد قبل الإرسال"):
    def __init__(self, item, draft, message_id=None):
        super().__init__()
        self.item = item
        self.message_id = message_id
        self.box = discord.ui.TextInput(label="الرد للضيف", style=discord.TextStyle.paragraph,
                                        default=draft, max_length=1800)
        self.add_item(self.box)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)   # ack now; sending can be slow
        text = str(self.box.value).strip()
        try:
            await asyncio.to_thread(send_guest_message, self.item["conversation_id"], text,
                                    self.item["comm_type"])
            try:
                msg = await interaction.channel.fetch_message(self.message_id)
                done = ApproveView()
                for c in done.children:
                    c.disabled = True
                await msg.edit(view=done)
            except Exception:
                pass
            _pending_replies.pop(self.message_id, None)
            _replied_msgs.add(self.message_id)
            await interaction.followup.send(
                f"✅ تم الإرسال (بعد التعديل) بواسطة {interaction.user.mention} "
                f"للضيف **{self.item['guest']}**.")
        except Exception as e:
            await interaction.followup.send(f"⚠️ فشل الإرسال: {e}", ephemeral=True)

# pending approval cards: discord_message_id -> {"item": item, "draft": draft}
_pending_replies = {}

def _recover_from_embed(message):
    """Rebuild (item, draft) from the card itself, so buttons work even after a full redeploy."""
    try:
        if not message.embeds:
            return None, None
        emb = message.embeds[0]
        foot = (emb.footer.text or "") if emb.footer else ""
        m = re.search(r"#(\d+)·(\S+)", foot)
        if not m:
            return None, None
        title = emb.title or ""
        guest = "الضيف"
        if "💬" in title:
            t = title.split("💬", 1)[1].strip()
            guest = (t.split("·", 1)[0].strip() or guest)
        draft = None
        for f in emb.fields:
            if "الرد المقترح" in (f.name or ""):
                draft = (f.value or "").strip()
        if not draft or draft == "—":
            return None, None
        return {"conversation_id": int(m.group(1)), "comm_type": m.group(2), "guest": guest}, draft
    except Exception as e:
        print("embed recover error:", e)
        return None, None

async def load_knowledge(guild):
    """Read the #knowledge channel and build the facts text the assistant uses."""
    global _knowledge_text
    ch = discord.utils.get(guild.text_channels, name=KNOWLEDGE_CHANNEL)
    if ch is None:
        return
    try:
        facts = []
        async for m in ch.history(limit=KNOWLEDGE_MAX, oldest_first=True):
            body = (m.content or "").strip()
            if body and not body.startswith(("/", "!")):   # skip commands
                facts.append(f"- {body}")
        _knowledge_text = "\n".join(facts)[:8000]
        print(f"knowledge: loaded {len(facts)} fact(s) from #{KNOWLEDGE_CHANNEL}")
    except Exception as e:
        print("knowledge load error:", e)

async def save_fact(guild, text):
    """Append a fact to the #knowledge channel (creating it if needed) and refresh."""
    ch = await ensure_channel(guild, KNOWLEDGE_CHANNEL, await get_assistant_category(guild))
    if ch is None:
        return False
    try:
        await ch.send(text[:1900])
        await load_knowledge(guild)
        return True
    except Exception as e:
        print("save fact error:", e)
        return False

class TeachModal(discord.ui.Modal, title="🧠 علّم المساعد معلومة"):
    def __init__(self, message_id, item=None):
        super().__init__()
        self.message_id = message_id
        self.item = item
        self.topic = discord.ui.TextInput(label="الموضوع (اختياري)", required=False,
                                          placeholder="مثال: واي فاي وحدة C08 / موقف السيارة",
                                          max_length=120)
        self.fact = discord.ui.TextInput(label="المعلومة الصحيحة", style=discord.TextStyle.paragraph,
                                         placeholder="اكتب المعلومة الصح اللي تبي المساعد يعرفها ويستخدمها.",
                                         max_length=900)
        self.add_item(self.topic)
        self.add_item(self.fact)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        topic = str(self.topic.value).strip()
        fact = str(self.fact.value).strip()
        line = f"**{topic}**: {fact}" if topic else fact
        ok = await save_fact(interaction.guild, line)
        if not ok:
            await interaction.followup.send("⚠️ تعذّر حفظ المعلومة.", ephemeral=True)
            return
        # regenerate this card's draft using the new knowledge (if we still have context)
        data = _pending_replies.get(self.message_id)
        item = (data or {}).get("item") or self.item
        regen = False
        if item and item.get("history"):
            try:
                result = await asyncio.to_thread(
                    claude_draft, item["guest"], item["unit"], item["history"],
                    (data or {}).get("guide"), (data or {}).get("confirmed", False))
                reply = (result or {}).get("reply", "").strip()
                if reply:
                    msg = await interaction.channel.fetch_message(self.message_id)
                    emb = msg.embeds[0]
                    fields = emb.fields
                    emb.clear_fields()
                    for f in fields:
                        emb.add_field(name=f.name,
                                      value=(reply[:1024] if "الرد المقترح" in f.name else f.value),
                                      inline=f.inline)
                    await msg.edit(embed=emb, view=ApproveView())
                    if data:
                        data["draft"] = reply
                    else:
                        _pending_replies[self.message_id] = {"item": item, "draft": reply,
                                                             "guide": (data or {}).get("guide"),
                                                             "confirmed": (data or {}).get("confirmed", False)}
                    regen = True
            except Exception as e:
                print("teach regen error:", e)
        note = "✅ حفظت المعلومة" + (" وأعدت صياغة الرد بها 👆" if regen else " — بتنطبق على الردود الجاية.")
        await interaction.followup.send(note, ephemeral=True)

class ConfirmActionView(discord.ui.View):
    """Ephemeral 'are you sure?' shown before a Send or Reject actually happens."""
    def __init__(self, action, channel_id, message_id):
        super().__init__(timeout=120)
        self.action = action            # "send" or "reject"
        self.channel_id = channel_id
        self.message_id = message_id

    async def _disable_card(self, interaction):
        try:
            ch = interaction.client.get_channel(self.channel_id)
            card = await ch.fetch_message(self.message_id)
            done = ApproveView()
            for c in done.children:
                c.disabled = True
            await card.edit(view=done)
        except Exception as e:
            print("confirm card edit error:", e)

    @discord.ui.button(label="✅ نعم، أكمل", style=discord.ButtonStyle.success)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.action == "send":
            data = _pending_replies.get(self.message_id)
            item = (data or {}).get("item")
            draft = (data or {}).get("draft")
            if not item:
                try:
                    ch = interaction.client.get_channel(self.channel_id)
                    card = await ch.fetch_message(self.message_id)
                    item, draft = _recover_from_embed(card)
                except Exception:
                    item = None
            if not item:
                await interaction.response.edit_message(
                    content="⚠️ هذا الكرت قديم — تعامل مع الرسالة يدوياً.", view=None)
                return
            await interaction.response.edit_message(content="⏳ جاري الإرسال…", view=None)
            try:
                await asyncio.to_thread(send_guest_message, item["conversation_id"], draft,
                                        item["comm_type"])
                await self._disable_card(interaction)
                _pending_replies.pop(self.message_id, None)
                _replied_msgs.add(self.message_id)
                await interaction.followup.send(
                    f"✅ تم الإرسال بواسطة {interaction.user.mention} للضيف **{item['guest']}**.")
            except Exception as e:
                await interaction.followup.send(f"⚠️ فشل الإرسال: {e}", ephemeral=True)
        else:   # reject
            await self._disable_card(interaction)
            _pending_replies.pop(self.message_id, None)
            _replied_msgs.add(self.message_id)
            await interaction.response.edit_message(content="🗑️ تم التجاهل.", view=None)
            await interaction.followup.send(f"🗑️ تم التجاهل بواسطة {interaction.user.mention}.")

    @discord.ui.button(label="✖️ تراجع", style=discord.ButtonStyle.secondary)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="تمام، ما سويت شي. الكرت زي ما هو 👍", view=None)

class PriceConfirmView(discord.ui.View):
    """Ephemeral 'are you sure?' before writing prices to the calendar."""
    def __init__(self, card_message_id):
        super().__init__(timeout=300)
        self.card_message_id = card_message_id

    @discord.ui.button(label="✅ نعم، طبّق", style=discord.ButtonStyle.success)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        opp = _price_opps.get(self.card_message_id)
        if not opp:
            await interaction.response.edit_message(
                content="انتهت صلاحية هالبطاقة — اطلب تقرير جديد.", view=None)
            return
        await interaction.response.edit_message(content="⏳ جاري تطبيق الأسعار…", view=None)
        applied, skipped, _results = await asyncio.to_thread(
            apply_price_changes, opp["listing_id"], opp["changes"])
        _price_opps.pop(self.card_message_id, None)
        tail = (" — (تجربة DRY-RUN، ما تغيّر شي فعلي)" if PRICE_APPLY_DRYRUN else "")
        skip_txt = f" · تخطّيت {skipped} (محجوزة/تغيّرت)" if skipped else ""
        result = f"✅ طبّقت {applied} ليلة على **{opp['name']}**{skip_txt}{tail}"
        log_event("pricing", f"طبّق {applied} سعر على {opp['name']} بواسطة {interaction.user.display_name}"
                  + (" (DRY-RUN)" if PRICE_APPLY_DRYRUN else ""))
        await interaction.followup.send(result, ephemeral=True)
        try:
            card = await interaction.channel.fetch_message(self.card_message_id)
            emb = card.embeds[0] if card.embeds else discord.Embed()
            emb.color = 0x2ECC71
            emb.set_footer(text=f"{result} · بواسطة {interaction.user.display_name}")
            await card.edit(embed=emb, view=None)
        except Exception as e:
            print("price card update error:", e)

    @discord.ui.button(label="✖️ لا", style=discord.ButtonStyle.secondary)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="تمام، ما غيّرت شي 👍", view=None)

class PriceApplyView(discord.ui.View):
    """Persistent Apply/Skip buttons under each unit's pricing card."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ طبّق", style=discord.ButtonStyle.success,
                       custom_id="ouja_price_apply")
    async def apply(self, interaction: discord.Interaction, button: discord.ui.Button):
        opp = _price_opps.get(interaction.message.id)
        if not opp:
            await interaction.response.send_message(
                "هالبطاقة قديمة (البوت اتحدّث) — اطلب تقرير جديد بـ PRICE_OPP_TEST=1.",
                ephemeral=True)
            return
        n = len(opp["changes"])
        warn = ("\n⚠️ وضع التجربة شغّال — ما راح يتغيّر شي فعلي." if PRICE_APPLY_DRYRUN
                else "\n‼️ بيتغيّر السعر فعلياً في تقويمك (Airbnb/Hostaway).")
        await interaction.response.send_message(
            f"متأكد تبي تطبّق **{n}** تغيير سعر على **{opp['name']}**؟{warn}",
            view=PriceConfirmView(interaction.message.id), ephemeral=True)

    @discord.ui.button(label="❌ تجاهل", style=discord.ButtonStyle.secondary,
                       custom_id="ouja_price_skip")
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        _price_opps.pop(interaction.message.id, None)
        emb = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed()
        emb.color = 0x95A5A6
        emb.set_footer(text=f"❌ تم التجاهل بواسطة {interaction.user.display_name}")
        await interaction.response.edit_message(embed=emb, view=None)

class ApproveView(discord.ui.View):
    def __init__(self, item=None, draft=None):
        super().__init__(timeout=None)   # persistent — survives bot restarts
        self.item = item
        self.draft = draft

    def _resolve(self, interaction):
        data = _pending_replies.get(interaction.message.id)
        if data:
            return data["item"], data["draft"]
        if self.item:
            return self.item, self.draft     # same-session fallback
        return _recover_from_embed(interaction.message)   # rebuild after a redeploy

    @discord.ui.button(label="✅ إرسال", style=discord.ButtonStyle.success, custom_id="ouja_send")
    async def send(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.message.id in _replied_msgs:
            await interaction.response.send_message(
                "✅ تم التعامل مع هذا الرد مسبقاً (من اللوحة).", ephemeral=True)
            return
        item, draft = self._resolve(interaction)
        if not item:
            await interaction.response.send_message(
                "⚠️ هذا الكرت قديم (انعاد تشغيل البوت) — تجاهله وتعامل مع الرسالة يدوياً.",
                ephemeral=True)
            return
        preview = (draft or "")[:300]
        await interaction.response.send_message(
            f"📤 متأكد تبي ترسل هذا الرد للضيف **{item['guest']}**؟\n\n>>> {preview}",
            view=ConfirmActionView("send", interaction.channel.id, interaction.message.id),
            ephemeral=True)

    @discord.ui.button(label="✏️ تعديل وإرسال", style=discord.ButtonStyle.primary, custom_id="ouja_edit")
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        item, draft = self._resolve(interaction)
        if not item:
            await interaction.response.send_message(
                "⚠️ هذا الكرت قديم (انعاد تشغيل البوت) — تجاهله وتعامل يدوياً.", ephemeral=True)
            return
        await interaction.response.send_modal(EditModal(item, draft, interaction.message.id))

    @discord.ui.button(label="🗑️ رفض", style=discord.ButtonStyle.danger, custom_id="ouja_reject")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "🗑️ متأكد تبي ترفض هذا الكرت وتتجاهله؟",
            view=ConfirmActionView("reject", interaction.channel.id, interaction.message.id),
            ephemeral=True)

    @discord.ui.button(label="🧠 علّم", style=discord.ButtonStyle.secondary, custom_id="ouja_teach")
    async def teach(self, interaction: discord.Interaction, button: discord.ui.Button):
        item, _ = self._resolve(interaction)
        await interaction.response.send_modal(TeachModal(interaction.message.id, item))

_assistant_seen = _BoundedSet(maxlen=20000)

_SENTIMENT_AR = {"ok": "عادي", "upset": "غاضب/منزعج"}

async def post_assistant_card(channel, item, result, guide=None, confirmed=False):
    g = item["guest"]
    intent = result.get("intent", "—")
    sentiment = result.get("sentiment", "ok")
    sent_ar = _SENTIMENT_AR.get(sentiment, sentiment)
    conf = float(result.get("confidence", 0) or 0)
    action = result.get("action", "escalate")
    reply = (result.get("reply") or "").strip()
    escalate = action == "escalate" or sentiment == "upset" or conf < ESCALATE_BELOW

    # ---- needs a human: tell the guest it's escalated, then alert the team ----
    if escalate:
        embed = discord.Embed(title=f"🚨 تصعيد · {g} · {item['unit']}", color=0xD64545)
        embed.add_field(name="📩 الضيف يقول", value=(item["guest_text"] or "—")[:1000], inline=False)
        embed.add_field(name="🔴 يحتاج تدخل بشري",
                        value=result.get("reason", "تم التصعيد — تعامل معه يدوياً."), inline=False)
        cid = item["conversation_id"]
        if cid in _claimed_convos:
            embed.add_field(name="🙋 مستلمة",
                            value="الموضوع مستلم من أحد الفريق — ما أرسلنا رد تلقائي.", inline=False)
        elif ASSISTANT_ESC_ACK:
            _esc_ack_count[cid] = _esc_ack_count.get(cid, 0) + 1
            n = _esc_ack_count[cid]
            static = ASSISTANT_ACK_AR if _has_arabic(item["guest_text"]) else ASSISTANT_ACK_EN
            if n == 1:
                ack = static                       # first time: quick holding message
            else:                                  # repeat: empathetic, problem-specific
                ack = await asyncio.to_thread(claude_escalation_ack, g, item["unit"],
                                              item["history"], item["guest_text"]) or static
            try:
                await asyncio.to_thread(send_guest_message, cid, ack, item["comm_type"])
                _esc_sent_acks.setdefault(cid, []).append(ack)
                embed.add_field(name="📤 تم إبلاغ الضيف",
                                value=("رسالة طمأنة متعاطفة (متابعة)" if n > 1
                                       else "رسالة طمأنة إنه تم تصعيد طلبه للقسم المختص."),
                                inline=False)
            except Exception as e:
                embed.add_field(name="⚠️ تعذّر إبلاغ الضيف", value=str(e), inline=False)
        embed.set_footer(text=f"النوع: {intent} · المشاعر: {sent_ar} · الثقة: {round(conf*100)}% · "
                              f"يعاد التنبيه كل {ESCALATION_REPING_MIN} دقيقة لين يستلمه أحد")
        # post to the dedicated escalations channel and @mention the operation team
        guild = channel.guild
        esc_channel = await ensure_channel(guild, ESCALATION_CHANNEL,
                                           await get_assistant_category(guild))
        target = esc_channel or channel
        op_role = find_operation_role(guild)
        mention = op_role.mention if op_role else f"@{OPERATION_ROLE_NAME}"
        try:
            msg = await target.send(content=f"{mention} 🚨 تصعيد جديد يحتاج استلام",
                                    embed=embed, view=ClaimView(),
                                    allowed_mentions=discord.AllowedMentions(roles=True))
            _escalations[msg.id] = {"channel_id": target.id, "guest": g, "unit": item["unit"],
                                    "conversation_id": item["conversation_id"],
                                    "guest_text": item["guest_text"],
                                    "reason": result.get("reason", ""), "history": item["history"],
                                    "last_ping": time.time(), "attempts": 0, "claimed_by": None,
                                    "last_msg_id": item.get("message_id") or 0,
                                    "acks": list(_esc_sent_acks.get(item["conversation_id"], []))}
        except Exception as e:
            print("escalation post error:", e)
        return

    # ---- STAGE 1: confident enough -> send automatically, then post an FYI card ----
    can_auto = (ASSISTANT_AUTO and not escalate and bool(reply) and conf >= ASSISTANT_AUTO_CONF)
    if can_auto:
        try:
            await asyncio.to_thread(send_guest_message, item["conversation_id"], reply,
                                    item["comm_type"])
            embed = discord.Embed(title=f"⚡ رد تلقائي · {g} · {item['unit']}", color=0x3BA55D)
            embed.add_field(name="📩 الضيف يقول", value=(item["guest_text"] or "—")[:1000], inline=False)
            embed.add_field(name="✅ تم الرد تلقائياً (Stage 1)", value=reply[:1000], inline=False)
            embed.set_footer(text=f"النوع: {intent} · الثقة: {round(conf*100)}% · رد تلقائي للعلم")
            await channel.send(embed=embed)
            log_event("guest", f"رد تلقائي ({round(conf*100)}%) · {g} · {item['unit']}")
            # --- auto-reply audit: keep a record + post to the dedicated audit channel ---
            _auto_replies.appendleft({"ts": datetime.now(TZ).isoformat(timespec="seconds"),
                                      "guest": g, "unit": item["unit"], "conf": round(conf * 100),
                                      "guest_text": (item["guest_text"] or "")[:600], "reply": reply[:1000]})
            try:
                audit = await ensure_channel(channel.guild, AUTO_REPLY_CHANNEL,
                                             await get_assistant_category(channel.guild))
                if audit:
                    a = discord.Embed(title=f"⚡ {g} · {item['unit']}", color=0x3BA55D,
                                      timestamp=datetime.now(TZ))
                    a.add_field(name="📩 الضيف", value=(item["guest_text"] or "—")[:1000], inline=False)
                    a.add_field(name="🤍 رد المساعد (تلقائي)", value=reply[:1000], inline=False)
                    a.set_footer(text=f"ثقة {round(conf*100)}% · أُرسل بدون مراجعة")
                    await audit.send(embed=a)
            except Exception as e:
                print("auto-reply audit post error:", e)
            return
        except Exception as e:
            print("auto-send failed, falling back to approval:", e)
            # fall through to the approval card if the send failed

    # ---- needs approval: draft + buttons ----
    embed = discord.Embed(title=f"💬 {g} · {item['unit']}", color=GOLD)
    embed.add_field(name="📩 الضيف يقول", value=(item["guest_text"] or "—")[:1024], inline=False)
    embed.add_field(name="✍️ الرد المقترح", value=(reply or "—")[:1024], inline=False)
    embed.set_footer(text=f"النوع: {intent} · الثقة: {round(conf*100)}% · راجعه قبل الإرسال · "
                          f"التوقيع يُضاف تلقائياً · #{item['conversation_id']}·{item['comm_type']}")
    sent = await channel.send(embed=embed, view=ApproveView(item, reply))
    _pending_replies[sent.id] = {"item": item, "draft": reply, "guide": guide, "confirmed": confirmed,
                                 "intent": intent, "confidence": round(conf*100), "sentiment": sentiment}

async def process_assistant_item(it, channel):
    """Draft + post a card (or escalate) for ONE guest message. Shared by the poll
    loop and the webhook handler so both behave identically."""
    _assistant_seen.add(it["message_id"])
    if not it["guest_text"]:
        return
    status = it.get("res_status") or await asyncio.to_thread(
        get_reservation_status, it.get("reservation_id"))
    confirmed = status in CONFIRMED_STATUSES
    guide = (await asyncio.to_thread(get_guide_url, it.get("listing_id"))
             if (confirmed and it.get("listing_id")) else None)
    result = await asyncio.to_thread(
        claude_draft, it["guest"], it["unit"], it["history"], guide, confirmed,
        (it.get("checkin"), it.get("checkout")), it.get("listing_id"))
    if not result:
        return
    try:
        await post_assistant_card(channel, it, result, guide, confirmed)
        act = result.get("action", "reply")
        if act == "escalate" or result.get("sentiment") == "upset":
            log_event("escalation", f"تصعيد · {it['guest']} · {it['unit']}")
        else:
            log_event("guest", f"بطاقة رد ({act}) · {it['guest']} · {it['unit']}")
    except Exception as e:
        print("assistant card error:", e)

async def _assistant_channel():
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return None
    return await ensure_channel(guild, ASSISTANT_CHANNEL, await get_assistant_category(guild))

async def run_assistant_scan():
    """One full inbox scan (used by the poll loop and as a webhook fallback)."""
    if not ASSISTANT_ENABLED:
        return
    channel = await _assistant_channel()
    if channel is None:
        return
    try:
        items = await asyncio.to_thread(fetch_new_guest_messages, _assistant_seen, ASSISTANT_DEBUG)
    except Exception as e:
        print("assistant scan fetch error:", e)
        return
    for it in items:
        await process_assistant_item(it, channel)

@tasks.loop(minutes=ASSISTANT_POLL_MIN)
async def assistant_loop():
    try:
        await run_assistant_scan()
    except Exception as e:
        print("assistant_loop error:", e)

# ---------------- Stage 2: Hostaway webhook server ----------------
_web_runner = None

def _extract_conversation_id(payload):
    """Pull a conversationId out of Hostaway's webhook payload, trying common shapes.
    Returns None if we can't find one (caller then falls back to a full scan)."""
    if not isinstance(payload, dict):
        return None
    # top level
    for k in ("conversationId", "conversation_id"):
        if payload.get(k):
            return payload[k]
    body = payload.get("data") or payload.get("object") or payload.get("body") or {}
    if isinstance(body, dict):
        for k in ("conversationId", "conversation_id"):
            if body.get(k):
                return body[k]
        # if the event object itself is a conversation, its id IS the conversation id
        evt = str(payload.get("event") or payload.get("type") or payload.get("object") or "").lower()
        if "conversation" in evt and body.get("id"):
            return body["id"]
    return None

async def _process_conversation_now(conversation_id):
    """Handle a single conversation immediately (triggered by a webhook)."""
    await bot.wait_until_ready()
    if not ASSISTANT_ENABLED:
        return
    channel = await _assistant_channel()
    if channel is None:
        return
    it = await asyncio.to_thread(fetch_conversation_item, conversation_id, _assistant_seen)
    if it:
        print(f"webhook: processing conversation {conversation_id} ({it['guest']})")
        await process_assistant_item(it, channel)

async def _handle_hook(request):
    secret = request.match_info.get("secret", "")
    if secret != WEBHOOK_SECRET:
        return web.Response(status=403, text="forbidden")
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    cid = _extract_conversation_id(payload)
    if cid:
        asyncio.create_task(_process_conversation_now(cid))
    else:
        # couldn't parse a conversation id -> just scan recent inbox (still near-instant)
        asyncio.create_task(run_assistant_scan())
    return web.Response(status=200, text="ok")     # ack fast so Hostaway doesn't retry

async def _handle_health(request):
    return web.Response(status=200, text="Ouja bot is up")

# ---------------- Activity log (feeds the dashboard) ----------------
_activity = deque(maxlen=800)
_auto_replies = deque(maxlen=500)     # audit of Stage-1 auto-sent messages (guest msg + AI reply)
_pricing_strategies = {}              # lid -> active dynamic-pricing strategy state

def log_event(category, text):
    """Record something the bot did, for the dashboard's activity feed."""
    try:
        _activity.append({"ts": datetime.now(TZ).isoformat(timespec="seconds"),
                          "cat": category, "text": str(text)[:300]})
    except Exception:
        pass
    print(f"[{category}] {text}")

# ---------------- Dashboard: auth + cached analytics + API + page ----------------
_dash_cache = {}
_replied_msgs = set()        # guard so a reply isn't sent twice (Discord + dashboard)
_last_price_changes = {}     # lid -> [changes] from the latest pricing compute (for dashboard Apply)
_last_price_detail = {}      # lid -> {name, base, confidence, rows:[per-date decision + why]}

DASHBOARD_HTML = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0e1116">
<title>Ouja</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0e1116; --surface:#161a22; --surface2:#1d222c; --line:#262b35;
  --text:#ecedee; --text2:#a8adb7; --mut:#6c727c;
  --gold:#d4a854; --gold2:#b08a3e;
  --green:#3ecf8e; --red:#e25c5c; --blue:#5b9eff; --yellow:#e9b94a;
  --r:14px; --r-sm:10px;
}
html,body{font-family:-apple-system,BlinkMacSystemFont,"SF Pro","Segoe UI",Tahoma,sans-serif;background:var(--bg);color:var(--text);font-size:15px;line-height:1.5;min-height:100vh;-webkit-font-smoothing:antialiased}
body{padding:env(safe-area-inset-top) 0 env(safe-area-inset-bottom)}
button,input,textarea{font-family:inherit;font-size:inherit;color:inherit}
button{border:none;background:none;cursor:pointer;-webkit-tap-highlight-color:transparent}
input,textarea{background:var(--surface2);border:1px solid var(--line);color:var(--text);border-radius:var(--r-sm);padding:11px 13px;width:100%}
input:focus,textarea:focus{outline:none;border-color:var(--gold)}
textarea{min-height:80px;resize:vertical;line-height:1.55}

.wrap{max-width:680px;margin:0 auto;padding:18px 16px 100px}
#login{position:fixed;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px;padding:24px;background:var(--bg)}
#login .brand{font-size:30px;font-weight:700;color:var(--gold);letter-spacing:.5px}
#login input{max-width:320px;text-align:center;font-size:16px;padding:14px}
#login .err{color:var(--red);font-size:13px;min-height:20px}

header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:18px;padding:6px 2px}
.brand{font-size:22px;font-weight:700;color:var(--gold);letter-spacing:.3px;line-height:1}
.fresh{display:inline-flex;align-items:center;gap:6px;font-size:11px;color:var(--mut);margin-top:6px}
.dot{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 0 3px rgba(62,207,142,.18)}
.dot.warm{background:var(--yellow);box-shadow:0 0 0 3px rgba(233,185,74,.18)}
.tools{display:flex;gap:8px}
.icon-btn{width:38px;height:38px;border-radius:10px;background:var(--surface);border:1px solid var(--line);color:var(--text2);font-size:15px;display:inline-flex;align-items:center;justify-content:center;transition:.15s}
.icon-btn:hover{color:var(--gold);border-color:var(--gold2)}

.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:16px;margin-bottom:14px}
.card-title{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;font-size:14px;font-weight:600;color:var(--text2)}
.card-title .right{color:var(--mut);font-size:12px;font-weight:500}

.nums{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px}
.num{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:14px 12px}
.num .v{font-size:24px;font-weight:700;letter-spacing:-.5px;line-height:1.1}
.num .v.g{color:var(--gold)} .num .v.b{color:var(--blue)} .num .v.r{color:var(--red)} .num .v.ok{color:var(--green)}
.num .l{color:var(--mut);font-size:11.5px;margin-top:5px;font-weight:500}

.needs{border:1px solid var(--line);border-radius:var(--r);margin-bottom:14px;overflow:hidden;background:var(--surface)}
.needs.alert{background:linear-gradient(135deg,rgba(212,168,84,.07),rgba(212,168,84,.01))}
.needs-head{display:flex;justify-content:space-between;align-items:center;padding:14px 16px;border-bottom:1px solid var(--line)}
.needs-head:last-child{border-bottom:none}
.needs-head .h{font-weight:700;font-size:15px}
.needs-head .h.warn{color:var(--yellow)} .needs-head .h.danger{color:var(--red)} .needs-head .h.ok{color:var(--green)}
.needs-list{padding:4px 0}
.needs-item{padding:14px 16px;border-bottom:1px solid var(--line)}
.needs-item:last-child{border-bottom:none}
.needs-item-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:9px;gap:8px;flex-wrap:wrap}
.needs-item-who{font-weight:600;font-size:14.5px}
.needs-item-tag{font-size:11px;background:var(--surface2);color:var(--text2);padding:3px 9px;border-radius:6px}
.needs-item-text{color:var(--text2);font-size:13px;line-height:1.55;background:var(--surface2);border-radius:8px;padding:10px 12px;margin-bottom:10px;white-space:pre-wrap}
.needs-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.needs-actions input{flex:1;min-width:140px}

.btn{padding:9px 14px;border-radius:9px;font-size:13.5px;font-weight:600;display:inline-flex;align-items:center;gap:5px;transition:.15s}
.btn.primary{background:var(--gold);color:#1a1308}
.btn.primary:hover{background:var(--gold2)}
.btn.green{background:rgba(62,207,142,.13);color:var(--green);border:1px solid rgba(62,207,142,.25)}
.btn.green:hover{background:rgba(62,207,142,.2)}
.btn.red{background:rgba(226,92,92,.13);color:var(--red);border:1px solid rgba(226,92,92,.25)}
.btn.ghost{background:var(--surface2);color:var(--text2);border:1px solid var(--line)}
.btn:disabled{opacity:.5;cursor:default}

.more{margin-top:14px}
.more-head{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:13px 16px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;font-weight:600;color:var(--text2);font-size:14px;transition:.15s}
.more-head:hover{color:var(--gold);border-color:var(--gold2)}
.more-head .caret{font-size:14px;color:var(--mut);transition:transform .2s;display:inline-block}
.more.open .more-head .caret{transform:rotate(180deg)}
.more-body{display:none;padding:0}
.more.open .more-body{display:block;margin-top:8px}

.pill-list{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px}
.pill{background:var(--surface2);border:1px solid var(--line);border-radius:8px;padding:6px 10px;font-size:12.5px;display:inline-flex;gap:6px;align-items:center;max-width:100%}
.pill .who{font-weight:600;color:var(--text)}
.pill .what{color:var(--mut);font-size:11.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pill.in{border-color:rgba(62,207,142,.28)}
.pill.out{border-color:rgba(91,158,255,.28)}
.pill.empty{border-color:rgba(212,168,84,.28);color:var(--gold);font-weight:600}

.discount{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
.discount .state{font-size:13.5px;color:var(--text2)}
.discount .state b.on{color:var(--green)}
.discount .state b.off{color:var(--yellow)}

.list-item{padding:14px 0;border-bottom:1px solid var(--line)}
.list-item:last-child{border-bottom:none}
.list-item .top{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px;gap:8px;flex-wrap:wrap}
.list-item .name{font-weight:600;font-size:14px}
.list-item .meta{font-size:12px;color:var(--mut)}
.list-item .actions{margin-top:10px;display:flex;gap:8px;flex-wrap:wrap}

.log-item{display:grid;grid-template-columns:auto 1fr;gap:10px;padding:9px 0;border-bottom:1px solid var(--line);font-size:13px;align-items:start}
.log-item:last-child{border:none}
.log-item .ts{color:var(--mut);font-size:11px;white-space:nowrap}
.log-item .txt{color:var(--text2);line-height:1.55}

#toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%) translateY(20px);background:var(--surface);border:1px solid var(--line);color:var(--text);padding:11px 18px;border-radius:11px;font-size:13.5px;opacity:0;transition:.25s;pointer-events:none;z-index:200;box-shadow:0 16px 40px rgba(0,0,0,.5)}
#toast.show{opacity:1;transform:translateX(-50%) translateY(0)}

.sk{background:linear-gradient(90deg,var(--surface) 25%,var(--surface2) 50%,var(--surface) 75%);background-size:200% 100%;animation:sk 1.2s infinite;color:transparent!important;border-radius:6px;min-height:18px}
@keyframes sk{0%{background-position:200% 0}100%{background-position:-200% 0}}
.muted{color:var(--mut);font-size:12.5px}
.empty{color:var(--mut);text-align:center;padding:22px;font-size:13px}

table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:10px 8px;border-bottom:1px solid var(--line);text-align:start}
th{color:var(--mut);font-weight:600;font-size:11.5px}

.bar-chart{display:flex;gap:4px;align-items:flex-end;height:120px;margin-bottom:18px}
.bar-col{flex:1;display:flex;flex-direction:column;align-items:center;gap:4px;min-width:0}
.bar{width:100%;background:linear-gradient(180deg,var(--gold),var(--gold2));border-radius:4px 4px 0 0;min-height:4px}
.bar-label{color:var(--mut);font-size:10px}

@media (min-width: 700px){
  .wrap{max-width:920px;padding:24px 22px 100px}
  .num .v{font-size:30px}
}
</style>
</head>
<body>

<div id="login">
  <div class="brand">Ouja · عوجا</div>
  <input id="tok" type="password" placeholder="رمز الدخول · Access token" autocomplete="off" onkeydown="if(event.key==='Enter')saveTok()">
  <button class="btn primary" onclick="saveTok()" style="padding:13px 26px;font-size:14.5px">دخول · Enter</button>
  <div class="err" id="lerr"></div>
</div>

<div class="wrap" id="app" style="display:none">

  <header>
    <div>
      <div class="brand">عوجا</div>
      <div class="fresh"><span class="dot" id="dot"></span><span id="freshness"></span></div>
    </div>
    <div class="tools">
      <button class="icon-btn" onclick="toggleLang()" id="langBtn">EN</button>
      <button class="icon-btn" onclick="refresh()" id="refreshBtn" aria-label="refresh">↻</button>
      <button class="icon-btn" onclick="logout()" aria-label="logout">⎋</button>
    </div>
  </header>

  <div class="nums" id="nums"></div>

  <div class="needs" id="needs"><div class="needs-head"><span class="muted sk">—</span></div></div>

  <div class="card">
    <div class="card-title"><span id="t_today">اليوم</span><span class="right" id="t_today_date"></span></div>
    <div id="todayBody"><div class="empty sk">—</div></div>
  </div>

  <div class="card">
    <div class="card-title"><span id="t_discount">الخصومات التلقائية</span></div>
    <div class="discount" id="discountBox"><div class="muted">…</div></div>
  </div>

  <div class="more" id="more_pricing">
    <div class="more-head" onclick="toggleMore('pricing')"><span>💰 <span id="t_pricing">فرص التسعير</span> <span class="muted" id="prCount"></span></span><span class="caret">⌃</span></div>
    <div class="more-body card" id="pricingBody"></div>
  </div>

  <div class="more" id="more_strat">
    <div class="more-head" onclick="toggleMore('strat')"><span>📊 <span id="t_strat">الاستراتيجيات</span> <span class="muted" id="stratCount"></span></span><span class="caret">⌃</span></div>
    <div class="more-body card" id="stratBody"></div>
  </div>

  <div class="more" id="more_rev">
    <div class="more-head" onclick="toggleMore('rev')"><span>📈 <span id="t_rev">الأداء والإيراد</span></span><span class="caret">⌃</span></div>
    <div class="more-body card" id="revBody"></div>
  </div>

  <div class="more" id="more_auto">
    <div class="more-head" onclick="toggleMore('auto')"><span>⚡ <span id="t_auto">الردود التلقائية</span> <span class="muted" id="autoCount"></span></span><span class="caret">⌃</span></div>
    <div class="more-body card" id="autoBody"></div>
  </div>

  <div class="more" id="more_log">
    <div class="more-head" onclick="toggleMore('log')"><span>📋 <span id="t_log">سجل النشاط</span></span><span class="caret">⌃</span></div>
    <div class="more-body card" id="logBody"></div>
  </div>

</div>

<div id="toast"></div>

<script>
const TK='ouja_token';
const T={
  ar:{dir:'rtl', langBtn:'EN',
    today:'اليوم', discount:'الخصومات التلقائية', pricing:'فرص التسعير',
    strat:'الاستراتيجيات', rev:'الأداء والإيراد', auto:'الردود التلقائية', log:'سجل النشاط',
    needs_ok:'كل شي تمام · ما يبيك شي 🤍',
    needs_pending:'ردود تنتظر مراجعتك', needs_esc:'تصعيدات تحتاج استلام',
    rep_send:'إرسال', rep_reject:'تجاهل', rep_edit_ph:'عدّل الرد قبل الإرسال…',
    claim:'استلام', claim_ph:'اسمك…', claim_by:'مستلمة بواسطة',
    nights:'ليالي', occ_tonight:'مشغولة الليلة', empty_tonight:'فاضية الليلة',
    rev_30:'إيراد ٣٠ يوم', rev_7:'إيراد ٧ أيام',
    arrivals:'الوصول', departures:'المغادرة', tight:'تنظيف نفس اليوم',
    risk:'إيراد على الطاولة', no_arr:'ما فيه وصول', no_dep:'ما فيه مغادرة', no_empty:'كل الوحدات محجوزة 🎉',
    active:'الوحدات الفعّالة',
    disc_on:'شغّالة', disc_off:'متوقفة', disc_pause24:'إيقاف ٢٤ ساعة', disc_resume:'استئناف',
    disc_paused_until:'متوقفة لين',
    pr_empty:'ما فيه فرص تسعير حالياً', pr_apply:'طبّق', pr_confirm:'متأكد؟ بيتغيّر السعر فعلياً في تقويمك.',
    pr_change:'تغيير', pr_uplift:'إيراد إضافي تقديري',
    st_empty:'ما فيه استراتيجيات. لما تطبّق فرصة تسعير راح تبدأ وحدة هنا.',
    st_running:'شغّالة', st_done:'انتهت', st_stop:'إيقاف', st_booked:'محجوزة', st_open:'مفتوحة',
    rev_loading:'يحمّل الأرقام…', rev_month:'الإيراد الشهري (ر.س)', rev_units:'أداء الوحدات', rev_no:'ما فيه بيانات بعد',
    auto_empty:'ما رسل المساعد ردود تلقائية بعد',
    log_empty:'لا يوجد نشاط مسجّل',
    sent:'تم الإرسال ✅', rejected:'تم التجاهل', claimed:'تم الاستلام ✅', applied:'تم التطبيق ✅', err:'صار خطأ',
    fresh:'آخر تحديث', live:'مباشر',
    wrong:'رمز غير صحيح · Wrong token',
    u_unit:'الوحدة', u_occ:'إشغال', u_adr:'سعر', u_pace:'٣٠ي'
  },
  en:{dir:'ltr', langBtn:'ع',
    today:'Today', discount:'Auto-discounts', pricing:'Pricing opportunities',
    strat:'Strategies', rev:'Performance & revenue', auto:'Auto-replies', log:'Activity log',
    needs_ok:"You're all caught up 🤍",
    needs_pending:'Replies awaiting review', needs_esc:'Escalations to claim',
    rep_send:'Send', rep_reject:'Dismiss', rep_edit_ph:'Edit the reply before sending…',
    claim:'Claim', claim_ph:'Your name…', claim_by:'Claimed by',
    nights:'nights', occ_tonight:'Occupied tonight', empty_tonight:'Empty tonight',
    rev_30:'Revenue 30d', rev_7:'Revenue 7d',
    arrivals:'Arrivals', departures:'Departures', tight:'Same-day turnovers',
    risk:'Revenue on the table', no_arr:'No arrivals', no_dep:'No departures', no_empty:'Every unit booked 🎉',
    active:'Active units',
    disc_on:'Running', disc_off:'Paused', disc_pause24:'Pause 24h', disc_resume:'Resume',
    disc_paused_until:'Paused until',
    pr_empty:'No pricing opportunities right now', pr_apply:'Apply', pr_confirm:'Sure? This changes real prices in your calendar.',
    pr_change:'change', pr_uplift:'Est. extra revenue',
    st_empty:'No strategies yet. Apply a price opportunity and one will start here.',
    st_running:'Running', st_done:'Finished', st_stop:'Stop', st_booked:'booked', st_open:'open',
    rev_loading:'Loading…', rev_month:'Monthly revenue (SAR)', rev_units:'Unit performance', rev_no:'No data yet',
    auto_empty:"Assistant hasn't auto-sent anything yet",
    log_empty:'No activity yet',
    sent:'Sent ✅', rejected:'Dismissed', claimed:'Claimed ✅', applied:'Applied ✅', err:'Something went wrong',
    fresh:'Updated', live:'live',
    wrong:'Wrong token',
    u_unit:'Unit', u_occ:'Occ', u_adr:'Rate', u_pace:'30d'
  }
};
let L=localStorage.getItem('ouja_lang')||'ar';
const D={}; const openMore={};

function t(){return T[L]}
function tok(){return localStorage.getItem(TK)||''}
function saveTok(){localStorage.setItem(TK,document.getElementById('tok').value.trim());init()}
function logout(){localStorage.removeItem(TK);location.reload()}
function toggleLang(){L=(L==='ar'?'en':'ar');localStorage.setItem('ouja_lang',L);applyLang();renderAll()}
function toast(m){const e=document.getElementById('toast');e.textContent=m;e.classList.add('show');clearTimeout(e._t);e._t=setTimeout(function(){e.classList.remove('show')},2200)}
function esc(s){return (s==null?'':String(s)).replace(/[<>&]/g,function(c){return ({'<':'&lt;','>':'&gt;','&':'&amp;'})[c]})}
function fmt(n){return (n||0).toLocaleString('en-US')}

async function api(path){
  const r=await fetch(path+(path.indexOf('?')>=0?'&':'?')+'token='+encodeURIComponent(tok()));
  if(r.status===401)throw 'unauthorized';
  return r.json();
}
async function post(path,body){
  const r=await fetch(path+'?token='+encodeURIComponent(tok()),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});
  return r.json().catch(function(){return {}});
}

function applyLang(){
  document.documentElement.dir=t().dir;
  document.documentElement.lang=L;
  document.getElementById('langBtn').textContent=t().langBtn;
  const m={t_today:'today',t_discount:'discount',t_pricing:'pricing',t_strat:'strat',t_rev:'rev',t_auto:'auto',t_log:'log'};
  for(const id in m){const el=document.getElementById(id);if(el)el.textContent=t()[m[id]]}
}

async function init(){
  try{
    document.getElementById('lerr').textContent='';
    await api('/api/overview');
    document.getElementById('login').style.display='none';
    document.getElementById('app').style.display='block';
    applyLang();
    await loadAll();
    setInterval(loadAll,15000);
  }catch(e){
    document.getElementById('lerr').textContent=t().wrong;
  }
}

async function loadAll(){
  try{
    const results = await Promise.all([
      api('/api/overview'),
      api('/api/today'),
      api('/api/inbox'),
      api('/api/discount/status'),
      api('/api/log'),
      api('/api/autolog')
    ]);
    D.ov=results[0]; D.today=results[1]; D.inbox=results[2]; D.disc=results[3];
    D.log=(results[4]||{}).items||[]; D.auto=(results[5]||{}).items||[];
    renderAll();
  }catch(e){ if(e==='unauthorized'){logout()} }
}

function renderAll(){
  renderNums(); renderNeeds(); renderToday(); renderDiscount(); renderFresh();
  if(openMore.pricing)renderPricing();
  if(openMore.strat)renderStrategies();
  if(openMore.rev)renderRevenue();
  if(openMore.auto)renderAuto();
  if(openMore.log)renderLog();
  updateCounts();
}

function renderFresh(){
  const d=document.getElementById('dot');
  const ready=D.ov&&D.ov.ready!==false;
  d.className='dot'+(ready?'':' warm');
  const u=D.ov&&D.ov.updated?new Date(D.ov.updated*1000):null;
  const ts=u?u.toLocaleTimeString(L==='ar'?'ar-SA':'en-US',{hour:'2-digit',minute:'2-digit'}):'—';
  document.getElementById('freshness').textContent=t().fresh+' '+ts+' · '+t().live;
}

function renderNums(){
  const o=D.ov||{}, td=D.today||{};
  const occN=td.occupied||0, occT=td.active||o.active_units||0;
  const cards=[
    {v:occN+'/'+occT, l:t().occ_tonight, c:(occN>=occT*0.85?'ok':'b')},
    {v:fmt(o.rev_7)+' SAR', l:t().rev_7, c:'ok'},
    {v:(td.empty_n||0), l:t().empty_tonight, c:((td.empty_n||0)>0?'r':'ok')}
  ];
  document.getElementById('nums').innerHTML = cards.map(function(c){
    return '<div class="num"><div class="v '+c.c+'">'+c.v+'</div><div class="l">'+c.l+'</div></div>';
  }).join('');
}

function renderNeeds(){
  const ib=D.inbox||{replies:[],escalations:[]};
  const escs=(ib.escalations||[]).filter(function(e){return !e.claimed_by});
  const reps=ib.replies||[];
  const box=document.getElementById('needs');
  if(escs.length===0 && reps.length===0){
    box.className='needs';
    box.innerHTML='<div class="needs-head"><span class="h ok">✓ '+t().needs_ok+'</span></div>';
    return;
  }
  box.className='needs alert';
  let html='';
  if(escs.length){
    html += '<div class="needs-head"><span class="h danger">🚨 '+escs.length+' '+t().needs_esc+'</span></div>';
    html += '<div class="needs-list">';
    for(let i=0;i<escs.length;i++){
      const e=escs[i];
      html += '<div class="needs-item" id="esc_'+e.id+'">';
      html += '<div class="needs-item-top"><span class="needs-item-who">'+esc(e.guest||'')+'</span><span class="needs-item-tag">'+esc(e.unit||'')+'</span></div>';
      if(e.guest_text) html += '<div class="needs-item-text">'+esc(e.guest_text)+'</div>';
      if(e.reason) html += '<div class="muted" style="margin-bottom:10px">⚠ '+esc(e.reason)+'</div>';
      html += '<div class="needs-actions"><input id="cn_'+e.id+'" placeholder="'+t().claim_ph+'"><button class="btn primary" onclick="doClaim('+e.id+')">🙋 '+t().claim+'</button></div>';
      html += '</div>';
    }
    html += '</div>';
  }
  if(reps.length){
    html += '<div class="needs-head"><span class="h warn">💬 '+reps.length+' '+t().needs_pending+'</span></div>';
    html += '<div class="needs-list">';
    for(let i=0;i<reps.length;i++){
      const r=reps[i];
      html += '<div class="needs-item" id="rep_'+r.id+'">';
      html += '<div class="needs-item-top"><span class="needs-item-who">'+esc(r.guest||'')+'</span><span class="needs-item-tag">'+esc(r.unit||'')+'</span></div>';
      if(r.guest_text) html += '<div class="needs-item-text">'+esc(r.guest_text)+'</div>';
      html += '<textarea id="ta_'+r.id+'" placeholder="'+t().rep_edit_ph+'">'+esc(r.draft||'')+'</textarea>';
      html += '<div class="needs-actions" style="margin-top:10px"><button class="btn green" onclick="doSend('+r.id+')">✅ '+t().rep_send+'</button><button class="btn red" onclick="doReject('+r.id+')">🗑️ '+t().rep_reject+'</button></div>';
      html += '</div>';
    }
    html += '</div>';
  }
  box.innerHTML = html;
}

function renderToday(){
  const td=D.today||{};
  const dateEl=document.getElementById('t_today_date');
  if(td.date){
    try{ dateEl.textContent = new Date(td.date).toLocaleDateString(L==='ar'?'ar-SA':'en-US',{weekday:'short',day:'numeric',month:'short'}) }catch(_){ dateEl.textContent=td.date }
  }
  const arr=td.arrivals||[], dep=td.departures||[], em=td.empty||[];
  let html='';
  if(arr.length){
    html += '<div class="muted" style="margin-bottom:6px">🟢 '+t().arrivals+' ('+arr.length+')</div>';
    html += '<div class="pill-list">'+arr.map(function(a){return '<div class="pill in"><span class="who">'+esc(a.unit)+'</span><span class="what">· '+esc(a.guest)+' · '+a.nights+'n</span></div>'}).join('')+'</div>';
  }
  if(dep.length){
    html += '<div class="muted" style="margin-bottom:6px">🔵 '+t().departures+' ('+dep.length+')</div>';
    html += '<div class="pill-list">'+dep.map(function(d){return '<div class="pill out"><span class="who">'+esc(d.unit)+'</span><span class="what">· '+esc(d.guest)+'</span></div>'}).join('')+'</div>';
  }
  if(em.length){
    html += '<div class="muted" style="margin-bottom:6px">🏠 '+t().empty_tonight+' ('+em.length+')</div>';
    html += '<div class="pill-list">'+em.map(function(e){return '<div class="pill empty">'+esc(e.unit)+'</div>'}).join('')+'</div>';
  }
  if(!arr.length && !dep.length && !em.length) html = '<div class="empty">'+t().no_empty+'</div>';
  document.getElementById('todayBody').innerHTML = html;
}

function renderDiscount(){
  const d=D.disc||{}; const box=document.getElementById('discountBox');
  if(d.paused){
    const u=d.until_iso?d.until_iso.replace('T',' ').slice(0,16):'';
    box.innerHTML='<div class="state">'+t().disc_paused_until+' <b class="off">'+u+'</b></div><button class="btn green" onclick="doResume()">▶ '+t().disc_resume+'</button>';
  }else{
    box.innerHTML='<div class="state">'+t().discount+': <b class="on">'+t().disc_on+'</b></div><button class="btn ghost" onclick="doPause(24)">⏸ '+t().disc_pause24+'</button>';
  }
}

function updateCounts(){
  const a=D.auto||[]; const c=document.getElementById('autoCount');
  if(c) c.textContent = a.length?('· '+a.length):'';
}

function toggleMore(key){
  openMore[key] = !openMore[key];
  document.getElementById('more_'+key).classList.toggle('open', !!openMore[key]);
  if(openMore[key]){
    if(key==='pricing') loadPricing();
    else if(key==='strat') loadStrategies();
    else if(key==='rev') loadRevenue();
    else if(key==='auto') renderAuto();
    else if(key==='log') renderLog();
  }
}

async function loadPricing(){
  document.getElementById('pricingBody').innerHTML='<div class="empty sk">—</div>';
  try{ D.pr=await api('/api/pricing') }catch(_){ D.pr={loading:true} }
  renderPricing();
}
function renderPricing(){
  const d=D.pr, body=document.getElementById('pricingBody');
  if(!d||d.loading){body.innerHTML='<div class="empty">'+t().rev_loading+'</div>';return}
  const units=d.units||[];
  document.getElementById('prCount').textContent = units.length?('· '+units.length):'';
  if(!units.length){body.innerHTML='<div class="empty">'+t().pr_empty+'</div>';return}
  let html='<div class="muted" style="margin-bottom:12px">'+t().pr_uplift+': <b style="color:var(--gold)">~'+fmt(d.total_uplift)+' SAR</b></div>';
  for(let i=0;i<units.length;i++){
    const u=units[i];
    const changes=(u.raise||0)+(u.drop||0);
    html += '<div class="list-item">';
    html += '<div class="top"><span class="name">'+esc(u.name)+'</span><span class="meta">~'+fmt(u.uplift)+' SAR · '+u.confidence+'%</span></div>';
    html += '<div class="muted">'+changes+' '+t().pr_change+'</div>';
    html += '<div class="actions"><button class="btn primary" onclick="doApply('+u.lid+',this)">✅ '+t().pr_apply+'</button></div>';
    html += '</div>';
  }
  body.innerHTML = html;
}

async function loadStrategies(){
  document.getElementById('stratBody').innerHTML='<div class="empty sk">—</div>';
  try{ D.strat=await api('/api/strategies') }catch(_){ D.strat={items:[]} }
  renderStrategies();
}
function renderStrategies(){
  const d=D.strat||{items:[]}; const items=d.items||[]; const body=document.getElementById('stratBody');
  document.getElementById('stratCount').textContent = items.length?('· '+items.length):'';
  if(!items.length){body.innerHTML='<div class="empty">'+t().st_empty+'</div>';return}
  let html='';
  for(let i=0;i<items.length;i++){
    const s=items[i];
    const pill = s.active ? '<span style="color:var(--green);font-weight:600">● '+t().st_running+'</span>' : '<span class="muted">'+t().st_done+'</span>';
    html += '<div class="list-item">';
    html += '<div class="top"><span class="name">'+esc(s.name)+'</span>'+pill+'</div>';
    html += '<div class="muted">'+s.booked+'/'+s.total+' '+t().st_booked+' · '+s.changes_total+' '+t().pr_change+'</div>';
    if(s.active) html += '<div class="actions"><button class="btn red" onclick="doStopStrategy('+s.lid+')">⏹ '+t().st_stop+'</button></div>';
    html += '</div>';
  }
  body.innerHTML = html;
}

async function loadRevenue(){
  document.getElementById('revBody').innerHTML='<div class="empty">'+t().rev_loading+'</div>';
  try{ D.rev=await api('/api/revenue') }catch(_){ D.rev={loading:true} }
  renderRevenue();
}
function renderRevenue(){
  const d=D.rev, body=document.getElementById('revBody');
  if(!d||d.loading){body.innerHTML='<div class="empty">'+t().rev_loading+'</div>';return}
  if(!d.monthly||!d.monthly.length){body.innerHTML='<div class="empty">'+t().rev_no+'</div>';return}
  const months = d.monthly.slice(-12);
  const max = Math.max.apply(null, months.map(function(m){return m.rev}));
  let bars = months.map(function(m){
    const h = Math.max(4, (m.rev/max)*110);
    return '<div class="bar-col"><div class="bar" style="height:'+h+'px"></div><div class="bar-label">'+m.m.slice(5)+'</div></div>';
  }).join('');
  let html='<div class="muted" style="margin-bottom:8px">'+t().rev_month+'</div>';
  html += '<div class="bar-chart">'+bars+'</div>';
  const u=(d.units||[]).slice(0,15);
  if(u.length){
    html += '<div class="muted" style="margin-bottom:8px">'+t().rev_units+'</div>';
    html += '<table><tr><th>'+t().u_unit+'</th><th>'+t().u_occ+'</th><th>'+t().u_adr+'</th><th>'+t().u_pace+'</th></tr>';
    html += u.map(function(x){return '<tr><td>'+esc(x.name)+'</td><td>'+x.occ+'%</td><td>'+(x.adr||'-')+'</td><td>'+x.pace+'%</td></tr>'}).join('');
    html += '</table>';
  }
  body.innerHTML = html;
}

function renderAuto(){
  const items=D.auto||[]; const body=document.getElementById('autoBody');
  if(!items.length){body.innerHTML='<div class="empty">'+t().auto_empty+'</div>';return}
  body.innerHTML = items.slice(0,30).map(function(a){
    return '<div class="list-item"><div class="top"><span class="name">'+esc(a.guest)+'</span><span class="meta">'+a.conf+'% · '+esc((a.ts||'').replace('T',' ').slice(0,16))+'</span></div>'
      + '<div class="needs-item-text">'+esc(a.guest_text||'')+'</div>'
      + '<div class="needs-item-text" style="background:rgba(212,168,84,.07);border:1px solid rgba(212,168,84,.18)">'+esc(a.reply||'')+'</div></div>';
  }).join('');
}

function renderLog(){
  const items=D.log||[]; const body=document.getElementById('logBody');
  if(!items.length){body.innerHTML='<div class="empty">'+t().log_empty+'</div>';return}
  const ic={guest:'💬',escalation:'🚨',pricing:'💰',report:'📊'};
  body.innerHTML = items.slice(0,80).map(function(e){
    return '<div class="log-item"><span class="ts">'+esc((e.ts||'').replace('T',' ').slice(0,16))+' '+(ic[e.cat]||'•')+'</span><span class="txt">'+esc(e.text)+'</span></div>';
  }).join('');
}

async function refresh(){
  const b=document.getElementById('refreshBtn');
  b.style.transition='.6s'; b.style.transform='rotate(360deg)';
  await loadAll();
  if(openMore.pricing) await loadPricing();
  if(openMore.strat) await loadStrategies();
  if(openMore.rev) await loadRevenue();
  setTimeout(function(){b.style.transition='none';b.style.transform='none'},650);
}

async function doSend(id){
  const ta=document.getElementById('ta_'+id); const text=ta?ta.value:'';
  const r=await post('/api/send',{id:id, text:text});
  if(r.ok){ toast(t().sent); const el=document.getElementById('rep_'+id); if(el)el.remove(); loadAll() }
  else toast(r.error||t().err);
}
async function doReject(id){
  await post('/api/reject',{id:id}); toast(t().rejected);
  const el=document.getElementById('rep_'+id); if(el)el.remove(); loadAll();
}
async function doClaim(id){
  const inEl=document.getElementById('cn_'+id);
  const n=inEl?inEl.value:'';
  const r=await post('/api/claim',{id:id, name:n});
  if(r.ok){ toast(t().claimed); loadAll() } else toast(r.error||t().err);
}
async function doApply(lid, btn){
  if(!confirm(t().pr_confirm))return;
  btn.disabled=true; const o=btn.textContent; btn.textContent='…';
  const r=await post('/api/apply',{lid:lid});
  if(r.ok){ toast(t().applied+(r.dry_run?' (DRY-RUN)':'')+' · '+r.applied); loadPricing(); loadStrategies() }
  else toast(r.error||t().err);
  setTimeout(function(){btn.disabled=false;btn.textContent=o},900);
}
async function doStopStrategy(lid){
  await post('/api/strategy/stop',{lid:lid}); toast('⏹'); loadStrategies();
}
async function doPause(hours){
  const r=await post('/api/discount/pause',{hours:hours}); if(r.ok){ D.disc=r; renderDiscount() }
}
async function doResume(){
  const r=await post('/api/discount/resume',{}); if(r.ok){ D.disc=r; renderDiscount() }
}

if(tok()) init();
</script>
</body>
</html>"""

def _dash_auth(request):
    return bool(DASHBOARD_TOKEN) and (
        request.query.get("token") or request.headers.get("X-Token", "")) == DASHBOARD_TOKEN

def _json(data, status=200):
    return web.json_response(data, status=status,
                             dumps=lambda o: json.dumps(o, ensure_ascii=False))

def _cache_get(key):
    hit = _dash_cache.get(key)
    return hit[0] if hit else None

def _live_counts():
    return {"pending_cards": len(_pending_replies),
            "open_escalations": sum(1 for e in _escalations.values() if not e.get("claimed_by"))}

def fetch_inhouse(day):
    """Reservations overlapping `day` (arrived on/before, departing on/after) — a precise,
    bounded query (~one row per occupied/turning unit) so occupancy is always accurate."""
    try:
        data = api_get("/reservations", params={
            "arrivalEndDate": day.isoformat(),          # arrivalDate <= today
            "departureStartDate": day.isoformat(),      # departureDate >= today
            "limit": 200})
        return data.get("result", []) or []
    except Exception as e:
        print("in-house fetch error:", e)
        return []

def _compute_today():
    """The morning cockpit: arrivals, departures, who's empty tonight, same-day turnovers,
    and the revenue on the table. Occupancy comes from a targeted in-house query (accurate)."""
    today = datetime.now(TZ).date()
    listings = get_listings_map()
    rows = fetch_inhouse(today)
    if not rows:                                            # fallback to history if the query fails
        rows = [r for r in get_reservations_cached() if _res_realized(r)]
    print(f"today: in-house query returned {len(rows)} reservations")

    def nm(r):
        return listings.get(r.get("listingMapId")) or r.get("listingName") or f"unit-{r.get('listingMapId')}"

    arrivals, departures = [], []
    occ_lids, dep_lids, arr_lids = set(), set(), set()
    for r in rows:
        if not _res_realized(r):
            continue
        a, d = _parse_date(r.get("arrivalDate")), _parse_date(r.get("departureDate"))
        lid = r.get("listingMapId")
        if a == today:
            arrivals.append({"guest": r.get("guestName") or "Guest", "unit": nm(r),
                             "nights": _res_nights(r), "checkout": d.isoformat() if d else ""})
            arr_lids.add(lid)
        if d == today:
            departures.append({"guest": r.get("guestName") or "Guest", "unit": nm(r)})
            dep_lids.add(lid)
        if a and d and a <= today < d:
            occ_lids.add(lid)
    units = {u["id"]: u["name"] for u in _catalog_units if u.get("id")}
    active = len(units) or len(occ_lids)
    empty = [{"unit": units.get(lid, str(lid)), "lid": lid}
             for lid in units if lid not in occ_lids]
    tight = [units.get(lid, str(lid)) for lid in (dep_lids & arr_lids)]      # same-day turnover
    prices = [u.get("price") for u in _catalog_units if u.get("price")]
    avg = round(sum(prices) / len(prices)) if prices else 0
    return {"date": today.isoformat(), "active": active, "occupied": len(occ_lids),
            "arrivals": sorted(arrivals, key=lambda x: x["unit"]),
            "departures": sorted(departures, key=lambda x: x["unit"]),
            "empty": sorted(empty, key=lambda x: x["unit"])[:90], "empty_n": len(empty),
            "tight": tight, "avg": avg, "risk": len(empty) * avg,
            "pending_cards": len(_pending_replies),
            "open_escalations": sum(1 for e in _escalations.values() if not e.get("claimed_by"))}

def _compute_overview():
    today = datetime.now(TZ).date()
    reservations = get_reservations_cached()
    listings = get_listings_map()
    factors = compute_demand_factors(reservations)
    lw = compute_last_week(reservations, listings, factors)
    nights, _ = _explode_nights(reservations)
    d30 = today - timedelta(days=30)
    rev30 = sum(nl for _, d, nl in nights if d30 <= d < today)
    n30 = sum(1 for _, d, _2 in nights if d30 <= d < today)
    active = len(_catalog_units) or len(set(lid for lid, _, _2 in nights))
    occ30 = (n30 / (active * 30)) if active else 0
    ci = sum(1 for r in reservations if _res_realized(r) and _parse_date(r.get("arrivalDate")) == today)
    co = sum(1 for r in reservations if _res_realized(r) and _parse_date(r.get("departureDate")) == today)
    return {"active_units": active, "occ_30": round(occ30 * 100), "rev_30": round(rev30),
            "rev_7": round(lw["tot_rev"]), "occ_7": round(lw["occ"] * 100),
            "missed_7": round(lw["tot_missed"]), "pending_cards": len(_pending_replies),
            "open_escalations": sum(1 for e in _escalations.values() if not e.get("claimed_by")),
            "checkins_today": ci, "checkouts_today": co}

def _compute_revenue():
    reservations = get_reservations_cached()
    listings = get_listings_map()
    rep = compute_revenue_report(reservations, listings)
    nights, _ = _explode_nights(reservations)
    series = {}
    for _, d, nl in nights:
        series[f"{d.year}-{d.month:02d}"] = series.get(f"{d.year}-{d.month:02d}", 0) + nl
    monthly = [{"m": k, "rev": round(series[k])} for k in sorted(series)[-12:]]
    return {"monthly": monthly,
            "seasonality": [{"name": m["name"], "adr": round(m["adr"]), "index": round(m["index"], 2)}
                            for m in rep["months"]],
            "salary": {str(k): round(v, 2) for k, v in rep["salary"]["dom_index"].items()},
            "weak": rep["salary"]["weak_window"], "strong": rep["salary"]["strong_window"],
            "units": [{"name": u["name"], "occ": round(u["occ90"] * 100),
                       "adr": round(u["adr"]) if u["adr"] else 0, "pace": round((u["pace30"] or 0) * 100),
                       "reco": u["reco"], "label": u["label"]} for u in rep["units"]]}

def _compute_pricing():
    reservations = get_reservations_cached()
    if not _catalog_units:
        load_catalog(True)
    factors = compute_demand_factors(reservations)
    per_unit, _ = compute_price_opportunities(factors, _catalog_units)
    _last_price_changes.clear()
    _last_price_detail.clear()
    _WD_AR = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
    _WD_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    units = []
    for lid, p in sorted(per_unit.items(), key=lambda kv: kv[1]["uplift"], reverse=True):
        if not p["raise"] and not p["drop"]:
            continue
        _last_price_changes[lid] = _unit_changes(p)
        drows = []
        for r, kind in [(x, "raise") for x in p["raise"]] + [(x, "drop") for x in p["drop"]]:
            d = _parse_date(r["date"])
            mi = round(factors["month_index"].get(d.month, 1), 2) if d else 1
            di = round(factors["dom_index"].get(d.day, 1), 2) if d else 1
            wi = round(factors["dow_index"].get(d.weekday(), 1), 2) if d else 1
            drows.append({"date": r["date"], "wd_ar": _WD_AR[r["wd"]], "wd_en": _WD_EN[r["wd"]],
                          "current": r["current"], "proposed": (r["target"] if kind == "raise" else r["clear"]),
                          "kind": kind, "lead": r["lead"], "mi": mi, "di": di, "wi": wi})
        drows.sort(key=lambda x: x["date"])
        _last_price_detail[lid] = {"name": p["name"], "base": p.get("base", 0),
                                   "confidence": p.get("confidence", 50), "rows": drows}
        units.append({"lid": lid, "name": p["name"], "raise": len(p["raise"]), "drop": len(p["drop"]),
                      "uplift": round(p["uplift"]), "confidence": p.get("confidence", 50),
                      "base": p.get("base", 0)})
    return {"total_uplift": round(sum(p["uplift"] for p in per_unit.values())), "units": units[:40]}

async def _api_overview(request):
    if not _dash_auth(request):
        return _json({"error": "unauthorized"}, 401)
    data = dict(_cache_get("overview") or {})
    data.update(_live_counts())                 # these two are always real-time & cheap
    data["ready"] = _cache_get("overview") is not None
    data["updated"] = _dash_cache.get("overview", (None, 0))[1]
    return _json(data)

async def _api_revenue(request):
    if not _dash_auth(request):
        return _json({"error": "unauthorized"}, 401)
    d = _cache_get("revenue")
    return _json(d if d else {"loading": True})

async def _api_pricing(request):
    if not _dash_auth(request):
        return _json({"error": "unauthorized"}, 401)
    d = _cache_get("pricing")
    return _json(d if d else {"loading": True})

async def _api_log(request):
    if not _dash_auth(request):
        return _json({"error": "unauthorized"}, 401)
    cat = request.query.get("cat", "")
    items = [e for e in reversed(_activity) if not cat or e["cat"] == cat][:200]
    return _json({"items": items})

async def _api_autolog(request):
    if not _dash_auth(request):
        return _json({"error": "unauthorized"}, 401)
    return _json({"items": list(_auto_replies)[:200]})

async def _api_today(request):
    if not _dash_auth(request):
        return _json({"error": "unauthorized"}, 401)
    d = dict(_cache_get("today") or {})
    d.update(_live_counts())                 # escalations + pending always real-time
    d["ready"] = _cache_get("today") is not None
    return _json(d if d.get("ready") else {"loading": True, **_live_counts()})

async def _api_inbox(request):
    """Live mirror of what the team is acting on: pending replies + open escalations."""
    if not _dash_auth(request):
        return _json({"error": "unauthorized"}, 401)
    replies = []
    for mid, d in list(_pending_replies.items()):
        it = d.get("item", {})
        replies.append({"id": mid, "guest": it.get("guest", "Guest"), "unit": it.get("unit", ""),
                        "guest_text": (it.get("guest_text") or "")[:600],
                        "thread": (it.get("history") or "")[:2500],
                        "time": it.get("last_time", ""),
                        "draft": (d.get("draft") or "")[:1200]})
    escs = []
    for eid, e in list(_escalations.items()):
        escs.append({"id": eid, "guest": e.get("guest", ""), "unit": e.get("unit", ""),
                     "reason": (e.get("reason") or "")[:400], "guest_text": (e.get("guest_text") or "")[:400],
                     "claimed_by": e.get("claimed_by")})
    return _json({"replies": replies, "escalations": escs})

async def _read_body(request):
    try:
        return await request.json()
    except Exception:
        return {}

async def _api_send(request):
    if not _dash_auth(request):
        return _json({"error": "unauthorized"}, 401)
    b = await _read_body(request)
    try:
        mid = int(b.get("id"))
    except Exception:
        return _json({"error": "bad id"}, 400)
    if mid in _replied_msgs:
        return _json({"error": "already handled"}, 409)
    data = _pending_replies.pop(mid, None)
    if not data:
        return _json({"error": "not found / already handled"}, 409)
    _replied_msgs.add(mid)
    item = data["item"]
    reply = (b.get("text") or data.get("draft") or "").strip()
    try:
        await asyncio.to_thread(send_guest_message, item["conversation_id"], reply,
                                item.get("comm_type", "email"))
        log_event("guest", f"رد (من اللوحة) · {item.get('guest','')} · {item.get('unit','')}")
        return _json({"ok": True})
    except Exception as e:
        return _json({"error": str(e)}, 500)

async def _api_reject(request):
    if not _dash_auth(request):
        return _json({"error": "unauthorized"}, 401)
    b = await _read_body(request)
    try:
        mid = int(b.get("id"))
    except Exception:
        return _json({"error": "bad id"}, 400)
    _replied_msgs.add(mid)
    data = _pending_replies.pop(mid, None)
    if data:
        log_event("guest", f"تجاهل رد (من اللوحة) · {data.get('item',{}).get('guest','')}")
    return _json({"ok": True})

async def _api_claim(request):
    if not _dash_auth(request):
        return _json({"error": "unauthorized"}, 401)
    b = await _read_body(request)
    try:
        eid = int(b.get("id"))
    except Exception:
        return _json({"error": "bad id"}, 400)
    name = (b.get("name") or "الفريق").strip()
    e = _escalations.get(eid)
    if not e:
        return _json({"error": "not found"}, 409)
    if e.get("claimed_by"):
        return _json({"error": f"already claimed by {e['claimed_by']}"}, 409)
    e["claimed_by"] = name
    if e.get("conversation_id"):
        _claimed_convos.add(e["conversation_id"])
    log_event("escalation", f"استلام تصعيد (من اللوحة) بواسطة {name} · {e.get('unit','')}")
    return _json({"ok": True})

async def _api_apply(request):
    if not _dash_auth(request):
        return _json({"error": "unauthorized"}, 401)
    b = await _read_body(request)
    try:
        lid = int(b.get("lid"))
    except Exception:
        return _json({"error": "bad lid"}, 400)
    changes = _last_price_changes.get(lid)
    if not changes:                                    # fall back to the detail rows
        det = _last_price_detail.get(lid)
        if det and det.get("rows"):
            changes = [{"date": r["date"], "price": r["proposed"], "kind": r["kind"]}
                       for r in det["rows"]]
    if not changes:
        return _json({"error": "no pending changes (refresh pricing first)"}, 409)
    applied, skipped, results = await asyncio.to_thread(apply_price_changes, lid, changes)
    _last_price_changes.pop(lid, None)
    if PRICING_STRATEGY_ENABLED and activate_strategy(lid, applied):
        asyncio.create_task(_kick_strategy(lid))   # run one pass now so the page isn't blank
    name = next((u["name"] for u in _catalog_units if u.get("id") == lid), str(lid))
    log_event("pricing", f"طبّق {applied} سعر (من اللوحة) · {name}"
              + (" (DRY-RUN)" if PRICE_APPLY_DRYRUN else ""))
    return _json({"ok": True, "applied": applied, "skipped": skipped,
                  "dry_run": PRICE_APPLY_DRYRUN, "results": results})

async def _handle_dashboard(request):
    return web.Response(text=DASHBOARD_HTML, content_type="text/html")

async def _api_pricing_detail(request):
    if not _dash_auth(request):
        return _json({"error": "unauthorized"}, 401)
    try:
        lid = int(request.query.get("lid"))
    except Exception:
        return _json({"error": "bad lid"}, 400)
    return _json(_last_price_detail.get(lid) or {"rows": []})

def _strategy_price(base, d, factors):
    """Best-number price for one night: demand target, stepped down as the night nears while empty."""
    mi = factors["month_index"].get(d.month, 1)
    di = factors["dom_index"].get(d.day, 1)
    wi = factors["dow_index"].get(d.weekday(), 1)
    target = max(0.6 * base, min(1.8 * base, base * mi * di * wi))
    lead = (d - datetime.now(TZ).date()).days
    f = 0.80 if lead <= 2 else 0.86 if lead <= 5 else 0.92 if lead <= 10 else 0.97 if lead <= 20 else 1.0
    return int(round(max(0.6 * base, target * f)))

def activate_strategy(lid, applied=0):
    """Start (or refresh) an active pricing strategy for a unit from its latest detail rows."""
    det = _last_price_detail.get(lid)
    if not det or not det.get("rows"):
        return False
    dates = {}
    for r in det["rows"]:
        p = r["proposed"]
        dates[r["date"]] = {"start": p, "cur": p, "booked": False, "changes": 0,
                            "last": datetime.now(TZ).isoformat(timespec="minutes")}
    prev = _pricing_strategies.get(lid, {})
    _pricing_strategies[lid] = {"name": det.get("name", str(lid)), "base": det.get("base", 0),
                                "started": prev.get("started") or datetime.now(TZ).isoformat(timespec="minutes"),
                                "updated": time.time(), "active": True, "dates": dates,
                                "applied_start": applied, "changes_total": prev.get("changes_total", 0),
                                "dry_at_start": PRICE_APPLY_DRYRUN}
    return True

async def _kick_strategy(lid):
    """Run a single optimization pass for one unit immediately (called right after Apply)."""
    try:
        strat = _pricing_strategies.get(lid)
        if not strat:
            return
        factors = await asyncio.to_thread(lambda: compute_demand_factors(get_reservations_cached()))
        await asyncio.to_thread(_run_strategy_unit, lid, strat, factors, datetime.now(TZ).date())
    except Exception as e:
        print(f"kick strategy {lid}:", e)

@tasks.loop(minutes=PRICING_STRATEGY_MIN)
async def pricing_strategy_loop():
    """Keep re-optimizing every active unit's open nights toward the best numbers."""
    if not (PRICING_STRATEGY_ENABLED and any(s.get("active") for s in _pricing_strategies.values())):
        return
    try:
        factors = await asyncio.to_thread(lambda: compute_demand_factors(get_reservations_cached()))
    except Exception as e:
        print("strategy factors error:", e)
        return
    today = datetime.now(TZ).date()
    for lid, strat in list(_pricing_strategies.items()):
        if not strat.get("active"):
            continue
        try:
            await asyncio.to_thread(_run_strategy_unit, lid, strat, factors, today)
        except Exception as e:
            print(f"strategy unit {lid} error:", e)

def _run_strategy_unit(lid, strat, factors, today):
    dates = strat["dates"]
    future = [d for d in dates if (_parse_date(d) or today) >= today]
    if not future:
        strat["active"] = False
        return
    ds = sorted(_parse_date(d) for d in future)
    booked_now = {}
    try:
        cal = api_get(f"/listings/{lid}/calendar",
                      params={"startDate": ds[0].isoformat(), "endDate": ds[-1].isoformat()})
        for day in (cal.get("result") or []):
            booked_now[day.get("date")] = (int(day.get("isAvailable", 0) or 0) != 1
                                           or bool(day.get("reservationId")))
    except Exception as e:
        print("strategy calendar error:", e)
        return
    base = strat.get("base") or factors["overall_adr"]
    for dstr in future:
        d = _parse_date(dstr)
        if d < today:
            continue
        rec = dates[dstr]
        if booked_now.get(dstr):                       # it sold — success, stop managing it
            if not rec["booked"]:
                rec["booked"] = True
                rec["last"] = datetime.now(TZ).isoformat(timespec="minutes")
                log_event("pricing", f"استراتيجية · انحجزت ليلة {dstr} · {strat['name']} ✅")
            continue
        want = _strategy_price(base, d, factors)
        cur = rec.get("cur") or want
        if cur and abs(want - cur) / cur >= 0.03:       # only meaningful moves
            if not PRICE_APPLY_DRYRUN:
                try:
                    api_put(f"/listings/{lid}/calendar",
                            {"startDate": dstr, "endDate": dstr, "isAvailable": 1,
                             "price": want, "note": f"ouja-orig:{want}"})
                except Exception as e:
                    print(f"strategy put {lid} {dstr}:", e)
                    continue
            rec["cur"] = want
            rec["changes"] = rec.get("changes", 0) + 1
            rec["last"] = datetime.now(TZ).isoformat(timespec="minutes")
            strat["changes_total"] = strat.get("changes_total", 0) + 1
    strat["updated"] = time.time()
    if all(rec["booked"] or (_parse_date(d) and _parse_date(d) < today) for d, rec in dates.items()):
        strat["active"] = False

def _strategy_view(lid):
    """Strategy detail with per-night before/after + the 'why' (month/dom/dow factors +
    lead-time discount) so the dashboard can elaborate each price decision."""
    s = _pricing_strategies.get(lid)
    if not s:
        return {"active": False, "dates": []}
    # compute factors once so we can attach per-night reasoning to the rows
    try:
        factors = compute_demand_factors(get_reservations_cached())
    except Exception:
        factors = {"month_index": {}, "dom_index": {}, "dow_index": {}, "overall_adr": 0}
    today = datetime.now(TZ).date()
    _WD_AR = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
    _WD_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    rows = []
    for d_str, r in s["dates"].items():
        d = _parse_date(d_str)
        if not d:
            continue
        lead = (d - today).days
        mi = round(factors["month_index"].get(d.month, 1), 2) if d else 1
        di = round(factors["dom_index"].get(d.day, 1), 2) if d else 1
        wi = round(factors["dow_index"].get(d.weekday(), 1), 2) if d else 1
        lead_factor = (0.80 if lead <= 2 else 0.86 if lead <= 5 else
                       0.92 if lead <= 10 else 0.97 if lead <= 20 else 1.0)
        rows.append({
            "date": d_str, "wd_ar": _WD_AR[d.weekday()], "wd_en": _WD_EN[d.weekday()],
            "lead": lead, "start": r["start"], "cur": r["cur"],
            "booked": r["booked"], "changes": r.get("changes", 0),
            "last": r.get("last", ""),
            "mi": mi, "di": di, "wi": wi, "lead_factor": lead_factor,
        })
    rows.sort(key=lambda x: x["date"])
    booked = sum(1 for r in rows if r["booked"])
    return {"name": s.get("name"), "base": s.get("base"), "active": s.get("active", False),
            "started": s.get("started"), "updated": s.get("updated", 0),
            "interval": PRICING_STRATEGY_MIN, "dry_run": PRICE_APPLY_DRYRUN,
            "applied_start": s.get("applied_start", 0), "changes_total": s.get("changes_total", 0),
            "total": len(rows), "booked": booked, "open": len(rows) - booked, "dates": rows}

def _strategies_list():
    """Summary of every strategy (active + finished) for the standing Strategies page."""
    out = []
    for lid, s in _pricing_strategies.items():
        dates = s.get("dates", {})
        booked = sum(1 for r in dates.values() if r.get("booked"))
        out.append({"lid": lid, "name": s.get("name", str(lid)), "base": s.get("base", 0),
                    "active": s.get("active", False), "started": s.get("started"),
                    "updated": s.get("updated", 0), "total": len(dates), "booked": booked,
                    "open": len(dates) - booked, "applied_start": s.get("applied_start", 0),
                    "changes_total": s.get("changes_total", 0),
                    "dry": s.get("dry_at_start", PRICE_APPLY_DRYRUN)})
    # active first, then most-recently-updated
    out.sort(key=lambda x: (not x["active"], -(x["updated"] or 0)))
    return out

async def _api_strategies(request):
    if not _dash_auth(request):
        return _json({"error": "unauthorized"}, 401)
    return _json({"items": _strategies_list(), "enabled": PRICING_STRATEGY_ENABLED,
                  "interval": PRICING_STRATEGY_MIN, "dry_run": PRICE_APPLY_DRYRUN})

async def _api_strategy(request):
    if not _dash_auth(request):
        return _json({"error": "unauthorized"}, 401)
    try:
        lid = int(request.query.get("lid"))
    except Exception:
        return _json({"error": "bad lid"}, 400)
    return _json(_strategy_view(lid))

async def _api_strategy_stop(request):
    if not _dash_auth(request):
        return _json({"error": "unauthorized"}, 401)
    b = await _read_body(request)
    try:
        lid = int(b.get("lid"))
    except Exception:
        return _json({"error": "bad lid"}, 400)
    s = _pricing_strategies.get(lid)
    if s:
        s["active"] = False
        log_event("pricing", f"إيقاف استراتيجية · {s.get('name', lid)}")
    return _json({"ok": True})

async def _api_discount_status(request):
    if not _dash_auth(request):
        return _json({"error": "unauthorized"}, 401)
    return _json(discount_pause_status())

async def _api_discount_pause(request):
    """POST {hours: N (default 24)} — pause discount tiers for N hours."""
    global _discount_paused_until
    if not _dash_auth(request):
        return _json({"error": "unauthorized"}, 401)
    b = await _read_body(request)
    try:
        hours = float(b.get("hours", 24))
    except Exception:
        hours = 24.0
    hours = max(0.5, min(168.0, hours))               # clamp 30 min … 7 days
    _discount_paused_until = time.time() + hours * 3600
    await asyncio.to_thread(persist_state)            # survive a redeploy
    log_event("pricing", f"إيقاف الخصومات لمدة {hours:g} ساعة")
    return _json({"ok": True, **discount_pause_status()})

async def _api_discount_resume(request):
    global _discount_paused_until
    if not _dash_auth(request):
        return _json({"error": "unauthorized"}, 401)
    _discount_paused_until = 0
    await asyncio.to_thread(persist_state)
    log_event("pricing", "استئناف الخصومات التلقائية")
    return _json({"ok": True, **discount_pause_status()})

# ---- per-unit discount skip (hold price on a specific apartment) ----
async def _api_unit_skip(request):
    """POST {lid, hours: N (default 24)} — skip discounts on this unit for N hours."""
    if not _dash_auth(request):
        return _json({"error": "unauthorized"}, 401)
    b = await _read_body(request)
    try:
        lid = int(b.get("lid"))
        hours = float(b.get("hours", 24))
    except Exception:
        return _json({"error": "bad params"}, 400)
    hours = max(0.5, min(168.0, hours))
    _unit_discount_skip[lid] = time.time() + hours * 3600
    await asyncio.to_thread(persist_state)
    name = next((u["name"] for u in _catalog_units if u.get("id") == lid), str(lid))
    log_event("pricing", f"تجاهل خصم {hours:g}س · {name}")
    return _json({"ok": True, "lid": lid, "until_iso": unit_skip_until_iso(lid)})

async def _api_unit_unskip(request):
    """POST {lid} — clear the skip on this unit."""
    if not _dash_auth(request):
        return _json({"error": "unauthorized"}, 401)
    b = await _read_body(request)
    try:
        lid = int(b.get("lid"))
    except Exception:
        return _json({"error": "bad lid"}, 400)
    _unit_discount_skip.pop(lid, None)
    await asyncio.to_thread(persist_state)
    name = next((u["name"] for u in _catalog_units if u.get("id") == lid), str(lid))
    log_event("pricing", f"إلغاء تجاهل الخصم · {name}")
    return _json({"ok": True})

async def _api_today_empty(request):
    """Per-unit empty-tonight detail: current price, scheduled tier prices, skip status."""
    if not _dash_auth(request):
        return _json({"error": "unauthorized"}, 401)
    items = await asyncio.to_thread(compute_tonight_empty)
    return _json({"items": items, "weekend": datetime.now(TZ).weekday() in WEEKEND_DAYS,
                  "paused": is_discount_paused(),
                  "paused_until_iso": discount_pause_status().get("until_iso", "")})

async def _api_inbox_detail(request):
    if not _dash_auth(request):
        return _json({"error": "unauthorized"}, 401)
    try:
        item_id = int(request.query.get("id"))
    except Exception:
        return _json({"error": "bad id"}, 400)
    detail = await asyncio.to_thread(get_inbox_item_detail, item_id)
    if not detail:
        return _json({"error": "not found"}, 404)
    return _json(detail)

async def _api_teach(request):
    """POST {topic, fact} — save a fact to the #knowledge Discord channel (mirrors the
    Discord 'علّم' modal). Future drafts pick it up after the next knowledge refresh."""
    if not _dash_auth(request):
        return _json({"error": "unauthorized"}, 401)
    b = await _read_body(request)
    topic = (b.get("topic") or "").strip()
    fact = (b.get("fact") or "").strip()
    if not fact:
        return _json({"error": "fact required"}, 400)
    line = f"**{topic}**: {fact}" if topic else fact
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return _json({"error": "discord guild not ready"}, 503)
    ok = await save_fact(guild, line)
    if ok:
        log_event("guest", f"تعلّم معلومة جديدة (من اللوحة): {(topic or fact)[:80]}")
    return _json({"ok": bool(ok)})

@tasks.loop(minutes=DASH_REFRESH_MIN)
async def dashboard_cache_loop():
    """Pre-compute heavy analytics in the background so the dashboard serves instantly."""
    if not (DASHBOARD_ENABLED and DASHBOARD_TOKEN):
        return
    try:
        if not _catalog_units:
            await asyncio.to_thread(load_catalog, True)
        ov = await asyncio.to_thread(_compute_overview)
        if ov.get("active_units") or ov.get("rev_30") or ov.get("rev_7"):  # don't cache empty
            _dash_cache["overview"] = (ov, time.time())
        rv = await asyncio.to_thread(_compute_revenue)
        if rv.get("monthly") or rv.get("units"):
            _dash_cache["revenue"] = (rv, time.time())
        td = await asyncio.to_thread(_compute_today)
        if td.get("active"):
            _dash_cache["today"] = (td, time.time())
        last = _dash_cache.get("pricing")
        if (not last) or (time.time() - last[1] > 1800):   # pricing is calendar-heavy: every ~30 min
            pr = await asyncio.to_thread(_compute_pricing)
            _dash_cache["pricing"] = (pr, time.time())
        print(f"dashboard cache warmed · units={ov.get('active_units')} rev30={ov.get('rev_30')}")
    except Exception as e:
        print("dashboard cache error:", e)

async def start_web_server():
    """Run a tiny HTTP server so Hostaway can push new-message events to us."""
    global _web_runner
    if _web_runner is not None or not _HAS_AIOHTTP:
        return
    app = web.Application()
    app.router.add_get("/", _handle_health)                 # health check / browser test
    app.router.add_post("/hook/{secret}", _handle_hook)     # Hostaway posts here
    app.router.add_get("/hook/{secret}", _handle_health)    # so you can open it in a browser
    if DASHBOARD_ENABLED:
        app.router.add_get("/dashboard", _handle_dashboard)
        app.router.add_get("/api/overview", _api_overview)
        app.router.add_get("/api/revenue", _api_revenue)
        app.router.add_get("/api/pricing", _api_pricing)
        app.router.add_get("/api/log", _api_log)
        app.router.add_get("/api/inbox", _api_inbox)
        app.router.add_get("/api/autolog", _api_autolog)
        app.router.add_get("/api/today", _api_today)
        app.router.add_get("/api/pricing/detail", _api_pricing_detail)
        app.router.add_get("/api/strategy", _api_strategy)
        app.router.add_get("/api/strategies", _api_strategies)
        app.router.add_post("/api/strategy/stop", _api_strategy_stop)
        app.router.add_get("/api/discount/status", _api_discount_status)
        app.router.add_post("/api/discount/pause", _api_discount_pause)
        app.router.add_post("/api/discount/resume", _api_discount_resume)
        app.router.add_post("/api/discount/skip-unit", _api_unit_skip)
        app.router.add_post("/api/discount/unskip-unit", _api_unit_unskip)
        app.router.add_get("/api/today/empty", _api_today_empty)
        app.router.add_get("/api/inbox/detail", _api_inbox_detail)
        app.router.add_post("/api/teach", _api_teach)
        app.router.add_post("/api/send", _api_send)
        app.router.add_post("/api/reject", _api_reject)
        app.router.add_post("/api/claim", _api_claim)
        app.router.add_post("/api/apply", _api_apply)
    _web_runner = web.AppRunner(app)
    await _web_runner.setup()
    site = web.TCPSite(_web_runner, "0.0.0.0", WEB_PORT)
    await site.start()
    print(f"web server listening on :{WEB_PORT}  (webhook path: /hook/{WEBHOOK_SECRET})")

def _cohost_responded(esc):
    """True if a human teammate replied to the guest directly since the escalation —
    an outbound message NEWER than the trigger that we didn't send ourselves."""
    cid = esc.get("conversation_id")
    if not cid:
        return False
    try:
        msgs = sorted((api_get(f"/conversations/{cid}/messages").get("result") or []),
                      key=lambda m: m.get("id", 0) or 0)
    except Exception:
        return False
    base = esc.get("last_msg_id", 0) or 0
    acks = esc.get("acks", [])
    for m in msgs:
        if (m.get("id", 0) or 0) <= base:
            continue                                   # not newer than the escalation trigger
        if _msg_is_inbound(m):
            continue                                   # guest's own message
        body = (m.get("body") or "").strip()
        if not body or _looks_automated(body):
            continue
        if any(a and a[:40] in body for a in acks):
            continue                                   # this is one of our own ack messages
        return True                                    # a human/co-host reply we didn't send
    return False

async def _resolve_escalation(mid, esc, reason="رد عليه أحد المضيفين"):
    """Stop nagging: mark resolved, free the conversation, and update the Discord card."""
    cid = esc.get("conversation_id")
    if cid:
        _claimed_convos.add(cid)
    _escalations.pop(mid, None)
    log_event("escalation", f"أُغلق تلقائياً ({reason}) · {esc.get('guest','')} · {esc.get('unit','')}")
    try:
        ch = bot.get_channel(esc.get("channel_id"))
        if ch:
            msg = await ch.fetch_message(mid)
            done = ClaimView()
            for c in done.children:
                c.disabled = True
            emb = msg.embeds[0] if msg.embeds else discord.Embed()
            emb.color = 0x3BA55D
            emb.add_field(name="✅ تم الإغلاق تلقائياً", value=reason, inline=False)
            await msg.edit(content=f"✅ تم التعامل معه — {reason}", embed=emb, view=done)
    except Exception as e:
        print("resolve-escalation edit error:", e)

@tasks.loop(minutes=1)
async def escalation_reping_loop():
    """Re-ping the operation team about any escalation that hasn't been claimed yet —
    but first auto-resolve any escalation where a co-host already replied (and stop nagging)."""
    if not _escalations:
        return
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return
    op_role = find_operation_role(guild)
    mention = op_role.mention if op_role else f"@{OPERATION_ROLE_NAME}"
    now = time.time()
    for mid, esc in list(_escalations.items()):
        if esc.get("claimed_by"):
            continue
        # --- auto-close if a teammate already answered the guest directly ---
        if await asyncio.to_thread(_cohost_responded, esc):
            await _resolve_escalation(mid, esc)
            continue
        if esc["attempts"] >= ESCALATION_MAX_PINGS:
            # we've nagged the max number of times and nobody picked it up — stop
            # silently sitting on the dashboard counter; mark it as exhausted so the
            # KPI reflects reality and the card carries a clear visual state.
            await _resolve_escalation(mid, esc, reason=f"انتهت محاولات التنبيه ({ESCALATION_MAX_PINGS}× بدون استلام)")
            continue
        if (now - esc["last_ping"]) < ESCALATION_REPING_MIN * 60:
            continue
        ch = bot.get_channel(esc["channel_id"])
        if ch is None:
            continue
        try:
            ref = discord.MessageReference(message_id=mid, channel_id=esc["channel_id"],
                                           fail_if_not_exists=False)
            await ch.send(f"{mention} ⏰ لسه ما تم استلام التصعيد — **{esc['guest']} · {esc['unit']}**. "
                          f"اضغط 🙋 أخذ المهمة.",
                          reference=ref, allowed_mentions=discord.AllowedMentions(roles=True))
            esc["last_ping"] = now
            esc["attempts"] += 1
        except Exception as e:
            print("reping error:", e)

@tasks.loop(minutes=KNOWLEDGE_REFRESH_MIN)
async def knowledge_loop():
    guild = bot.get_guild(GUILD_ID)
    if guild is not None:
        await load_knowledge(guild)
    await asyncio.to_thread(load_catalog)   # refreshes only if >1h old

def load_state():
    """Restore in-memory state from the volume so nothing is lost across restarts/redeploys."""
    global _assistant_seen, _pending_replies, _escalations, _esc_ack_count, _claimed_convos
    global _price_opps, _discount_paused_until, _unit_discount_skip
    try:
        _assistant_seen = _BoundedSet(_load_json("seen.json", []), maxlen=20000)
        _pending_replies = {int(k): v for k, v in _load_json("pending.json", {}).items()}
        _escalations = {int(k): v for k, v in _load_json("escalations.json", {}).items()}
        _esc_ack_count = {int(k): v for k, v in _load_json("ack_count.json", {}).items()}
        _claimed_convos = set(int(x) for x in _load_json("claimed.json", []))
        _activity.clear()
        _activity.extend(_load_json("activity.json", []))
        _auto_replies.clear()
        _auto_replies.extend(_load_json("auto_replies.json", []))
        _pricing_strategies.clear()
        _pricing_strategies.update({int(k): v for k, v in _load_json("strategies.json", {}).items()})
        _price_opps = {int(k): v for k, v in _load_json("price_opps.json", {}).items()}
        _discount_paused_until = float(_load_json("discount_pause.json", 0) or 0)
        _unit_discount_skip = {int(k): float(v) for k, v in _load_json("unit_discount_skip.json", {}).items()
                               if float(v) > time.time()}   # drop expired entries on boot
        if _assistant_seen or _pending_replies or _escalations:
            print(f"state: restored {len(_assistant_seen)} seen · {len(_pending_replies)} cards · "
                  f"{len(_escalations)} escalations · {len(_claimed_convos)} claimed · "
                  f"{len(_price_opps)} price cards")
    except Exception as e:
        print("state load error:", e)

def persist_state():
    _save_json("seen.json", list(_assistant_seen))
    _save_json("pending.json", {str(k): v for k, v in _pending_replies.items()})
    _save_json("escalations.json", {str(k): v for k, v in _escalations.items()})
    _save_json("ack_count.json", {str(k): v for k, v in _esc_ack_count.items()})
    _save_json("claimed.json", list(_claimed_convos))
    _save_json("activity.json", list(_activity))
    _save_json("auto_replies.json", list(_auto_replies))
    _save_json("strategies.json", {str(k): v for k, v in _pricing_strategies.items()})
    _save_json("price_opps.json", {str(k): v for k, v in _price_opps.items()})
    _save_json("discount_pause.json", _discount_paused_until)
    _save_json("unit_discount_skip.json", {str(k): v for k, v in _unit_discount_skip.items()})

@tasks.loop(seconds=60)
async def persist_loop():
    await asyncio.to_thread(persist_state)

# ==================== Weekly Revenue Report (recommend-only) ====================
# Pulls full booking history from Hostaway and produces a weekly Discord report:
#  (1) per-unit raise/hold/lower recommendation (optimizing TOTAL REVENUE),
#  (2) which months pay best/worst, (3) the real intra-month "salary cycle" dip.
# It NEVER changes prices — it only recommends. All numbers are computed in code.

def fetch_all_reservations(max_pages=None):
    """Paginate the full reservation history from Hostaway."""
    max_pages = max_pages or REVENUE_MAX_PAGES
    out, offset, limit = [], 0, 100
    for _ in range(max_pages):
        try:
            data = api_get("/reservations", params={"limit": limit, "offset": offset})
        except Exception as e:
            print("reservations fetch error:", e)
            break
        rows = data.get("result", []) or []
        if not rows:
            break
        out.extend(rows)
        if len(rows) < limit:
            break
        offset += limit
    if REVENUE_DEBUG and out:
        print("reservation sample keys:", sorted(out[0].keys()))
    print(f"revenue: fetched {len(out)} reservations")
    return out

def _res_nights(r):
    n = r.get("nights")
    if isinstance(n, int) and n > 0:
        return n
    ci, co = _parse_date(r.get("arrivalDate")), _parse_date(r.get("departureDate"))
    return (co - ci).days if (ci and co and co > ci) else 0

def _res_revenue(r):
    """Best-effort gross booking revenue (consistent across channels). Tune via REVENUE_DEBUG."""
    for k in ("totalPrice", "baseRate", "ownerPayout", "hostPayout", "price"):
        v = r.get(k)
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
    return 0.0

def _res_realized(r):
    return (r.get("status") or "").lower() in CONFIRMED_STATUSES

def _explode_nights(reservations):
    """Return (nights, arrivals): nights = list of (listing_id, date, nightly_price);
    arrivals = list of (listing_id, checkin_date)."""
    nights, arrivals = [], []
    for r in reservations:
        if not _res_realized(r):
            continue
        ci = _parse_date(r.get("arrivalDate"))
        n = _res_nights(r)
        if not ci or n <= 0:
            continue
        lid = r.get("listingMapId")
        nightly = _res_revenue(r) / n if n else 0
        arrivals.append((lid, ci))
        for i in range(n):
            nights.append((lid, ci + timedelta(days=i), nightly))
    return nights, arrivals

def _unit_reco(pace30, occ90, adr, adr_median):
    """Revenue-max heuristic -> (key, label_ar, reason_ar, suggested_pct)."""
    if pace30 is None:
        return ("watch", "🟡 راقب", "بيانات غير كافية", 0)
    p = round(pace30 * 100)
    if pace30 >= 0.85:
        return ("raise", "🔼 ارفع", f"يمتلئ بسرعة (محجوز {p}% من الـ٣٠ يوم الجاية) — فيه مجال ترفع", 12)
    if pace30 >= 0.65:
        return ("raise_small", "🔼 ارفع بسيط", f"طلب قوي (pace {p}%)", 6)
    if pace30 >= 0.40:
        if adr and adr_median and adr < 0.9 * adr_median and (occ90 or 0) >= 0.6:
            return ("raise_small", "🔼 ارفع بسيط", "سعرك أقل من متوسط المحفظة وإشغالك جيد", 5)
        return ("hold", "⏸️ ثابت", f"وضع متوازن (pace {p}%)", 0)
    if adr and adr_median and adr > 1.1 * adr_median:
        return ("lower", "🔽 خفّض", f"طلب ضعيف وسعرك أعلى من المتوسط (pace {p}%)", -12)
    return ("lower", "🔽 خفّض", f"طلب ضعيف للـ٣٠ يوم الجاية (pace {p}%)", -8)

_AR_MONTHS = ["", "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
              "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]

def compute_revenue_report(reservations, listings_map):
    """Crunch the history into per-unit recs + seasonality + salary-cycle. Pure/no I/O."""
    today = datetime.now(TZ).date()
    w_start = today - timedelta(days=REVENUE_WINDOW_DAYS)
    n30 = today + timedelta(days=30)
    y_start = today - timedelta(days=365)
    nights, arrivals = _explode_nights(reservations)

    # ---- per-unit: trailing-window occupancy/ADR + forward 30-day pace ----
    sold90, rev90, booked30 = defaultdict(int), defaultdict(float), defaultdict(int)
    for lid, d, nightly in nights:
        if w_start <= d < today:
            sold90[lid] += 1
            rev90[lid] += nightly
        if today <= d < n30:
            booked30[lid] += 1
    units = []
    adrs = []
    for lid in set(list(sold90) + list(booked30)):
        s = sold90[lid]
        adr = (rev90[lid] / s) if s else None
        if adr:
            adrs.append(adr)
    adr_median = sorted(adrs)[len(adrs) // 2] if adrs else None
    all_lids = set(list(sold90) + list(booked30))
    for lid in all_lids:
        s = sold90[lid]
        occ90 = s / REVENUE_WINDOW_DAYS
        adr = (rev90[lid] / s) if s else None
        pace30 = booked30[lid] / 30
        revpar = (rev90[lid] / REVENUE_WINDOW_DAYS) if REVENUE_WINDOW_DAYS else 0
        key, label, reason, pct = _unit_reco(pace30, occ90, adr, adr_median)
        units.append({
            "lid": lid, "name": listings_map.get(lid) or f"unit-{lid}",
            "occ90": occ90, "adr": adr, "revpar": revpar, "pace30": pace30,
            "reco": key, "label": label, "reason": reason, "pct": pct,
        })
    units.sort(key=lambda u: (u["pace30"] or 0), reverse=True)

    # ---- seasonality: avg nightly (ADR) + volume by month-of-year ----
    m_rev, m_nights = defaultdict(float), defaultdict(int)
    for lid, d, nightly in nights:
        m_rev[d.month] += nightly
        m_nights[d.month] += 1
    total_n = sum(m_nights.values())
    overall_adr = (sum(m_rev.values()) / total_n) if total_n else 0
    months = []
    for m in range(1, 13):
        if m_nights[m]:
            adr_m = m_rev[m] / m_nights[m]
            months.append({"m": m, "name": _AR_MONTHS[m], "adr": adr_m,
                           "nights": m_nights[m],
                           "index": (adr_m / overall_adr) if overall_adr else 1})
    months.sort(key=lambda x: x["index"], reverse=True)

    # ---- salary cycle: arrivals per day-of-month (last 365d), normalized by occurrences ----
    occ_count = defaultdict(int)        # how many calendar dates had each day-of-month
    d = y_start
    while d < today:
        occ_count[d.day] += 1
        d += timedelta(days=1)
    arr_by_dom = defaultdict(int)
    for lid, ci in arrivals:
        if y_start <= ci < today:
            arr_by_dom[ci.day] += 1
    rates = {dom: (arr_by_dom[dom] / occ_count[dom]) for dom in range(1, 32) if occ_count.get(dom)}
    mean_rate = (sum(arr_by_dom.values()) / sum(occ_count[d] for d in range(1, 32) if occ_count.get(d))) \
        if arr_by_dom else 0
    dom_index = {dom: (rates[dom] / mean_rate if mean_rate else 1) for dom in rates}
    # find the weakest/strongest contiguous run within days 1..28 (avoid month-end sparsity:
    # months with 30/31 days mean day 29-31 have ~half the samples and skew the index)
    weak_days = [dom for dom in range(1, 29) if dom_index.get(dom, 1) < 0.92]
    strong_days = [dom for dom in range(1, 29) if dom_index.get(dom, 1) > 1.08]

    def _run(days):
        if not days:
            return None
        best = cur = [days[0]]
        for x in days[1:]:
            if x == cur[-1] + 1:
                cur.append(x)
            else:
                if len(cur) > len(best):
                    best = cur
                cur = [x]
        if len(cur) > len(best):
            best = cur
        return (best[0], best[-1])

    salary = {
        "dom_index": dom_index,
        "weak_window": _run(weak_days),
        "strong_window": _run(strong_days),
        "have_data": bool(arr_by_dom),
    }
    return {"units": units, "months": months, "salary": salary,
            "overall_adr": overall_adr, "total_nights": total_n,
            "active": len(all_lids)}

def _pct(x):
    return f"{round((x - 1) * 100):+d}%"

def build_revenue_embeds(rep):
    """Turn the computed report into Discord embeds + a detail CSV (bytes)."""
    units = rep["units"]
    raises = [u for u in units if u["reco"] in ("raise", "raise_small")]
    lowers = [u for u in units if u["reco"] == "lower"]
    holds = [u for u in units if u["reco"] == "hold"]
    port_occ = (sum(u["occ90"] for u in units) / len(units)) if units else 0
    port_pace = (sum((u["pace30"] or 0) for u in units) / len(units)) if units else 0

    e1 = discord.Embed(
        title="📊 تقرير الإيرادات الأسبوعي · عوجا",
        description=(f"الوحدات الفعّالة: **{rep['active']}** · إشغال آخر {REVENUE_WINDOW_DAYS} يوم: "
                     f"**{round(port_occ*100)}%** · متوسط الحجز للـ٣٠ يوم الجاية: **{round(port_pace*100)}%** · "
                     f"متوسط السعر/الليلة: **{round(rep['overall_adr'])} ر.س**\n"
                     f"الهدف: **أعلى إيراد إجمالي** · *توصيات فقط — أنت تقرر التطبيق*"),
        color=GOLD)
    if raises:
        txt = "\n".join(f"• **{u['name']}** {u['label']} ~{u['pct']:+d}% — {u['reason']}"
                        for u in raises[:12])
        e1.add_field(name=f"🔼 ارفع السعر ({len(raises)})", value=txt[:1024], inline=False)
    if lowers:
        txt = "\n".join(f"• **{u['name']}** {u['pct']:+d}% — {u['reason']}" for u in lowers[:12])
        e1.add_field(name=f"🔽 خفّض السعر ({len(lowers)})", value=txt[:1024], inline=False)
    e1.add_field(name="⏸️ ثابت", value=f"{len(holds)} وحدة وضعها متوازن", inline=False)
    e1.set_footer(text="التفاصيل الكاملة لكل وحدة في الملف المرفق · الأسعار قبل الضريبة ورسوم المنصة")

    e2 = discord.Embed(title="🗓️ أقوى وأضعف الشهور (حسب متوسط السعر)", color=GOLD)
    if rep["months"]:
        top = rep["months"][:3]
        bot_ = rep["months"][-3:]
        e2.add_field(name="الأقوى",
                     value="\n".join(f"• {m['name']}: {round(m['adr'])} ر.س/ليلة ({_pct(m['index'])} عن المعدل)"
                                     for m in top) or "—", inline=False)
        e2.add_field(name="الأضعف",
                     value="\n".join(f"• {m['name']}: {round(m['adr'])} ر.س/ليلة ({_pct(m['index'])} عن المعدل)"
                                     for m in reversed(bot_)) or "—", inline=False)
        e2.set_footer(text="ارفع الأسعار الأساسية في الشهور القوية، وخفّفها في الضعيفة")

    s = rep["salary"]
    e3 = discord.Embed(title="💸 دورة الراتب داخل الشهر", color=GOLD)
    if s["have_data"]:
        parts = []
        ww, sw = s["weak_window"], s["strong_window"]
        if ww:
            a, b = ww
            avgw = sum(s["dom_index"].get(d, 1) for d in range(a, b + 1)) / (b - a + 1)
            parts.append(f"📉 الطلب يضعف في أيام **{a}–{b}** ({_pct(avgw)} عن المعدل) — اقتراح: خفّض "
                         f"~{min(12, round((1-avgw)*100))}% على الليالي اللي تقع في هالأيام.")
        if sw:
            a, b = sw
            avgs = sum(s["dom_index"].get(d, 1) for d in range(a, b + 1)) / (b - a + 1)
            parts.append(f"📈 الطلب يرتفع حول أيام **{a}–{b}** ({_pct(avgs)} عن المعدل) — اقتراح: ثبّت أو "
                         f"ارفع ~{min(12, round((avgs-1)*100))}% على هالأيام.")
        parts.append("ملاحظتك كانت: ضعف ٢٠–٢٤ والراتب يوم ٢٥ — فوق تشوف اللي طلعته بياناتك فعلياً.")
        e3.description = "\n\n".join(parts)
    else:
        e3.description = "ما فيه بيانات وصول كافية في آخر سنة لتحليل دورة الراتب بعد."

    # ---- detail CSV (every unit) ----
    rows = ["unit,occupancy_90d_%,ADR_SAR,RevPAR_SAR,pace_30d_%,recommendation,suggested_%"]
    for u in sorted(rep["units"], key=lambda x: (x["reco"] != "raise", x["name"])):
        rows.append(",".join([
            '"' + str(u["name"]).replace('"', "'") + '"',
            str(round(u["occ90"] * 100)),
            str(round(u["adr"])) if u["adr"] else "",
            str(round(u["revpar"])),
            str(round((u["pace30"] or 0) * 100)),
            u["reco"], str(u["pct"]),
        ]))
    csv_bytes = ("\n".join(rows)).encode("utf-8-sig")
    return [e1, e2, e3], csv_bytes

async def post_revenue_report():
    if not ASSISTANT_ENABLED:
        pass  # report doesn't require the assistant; keep running regardless
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return
    channel = await ensure_channel(guild, REVENUE_CHANNEL, await get_assistant_category(guild))
    if channel is None:
        return
    reservations = await asyncio.to_thread(fetch_all_reservations)
    if not reservations:
        await channel.send("⚠️ ما قدرت أجيب بيانات الحجوزات من Hostaway لهذا التقرير.")
        return
    listings_map = await asyncio.to_thread(get_listings_map)
    rep = await asyncio.to_thread(compute_revenue_report, reservations, listings_map)
    embeds, csv_bytes = build_revenue_embeds(rep)
    file = discord.File(io.BytesIO(csv_bytes), filename="ouja_revenue_detail.csv")
    await channel.send(embeds=embeds, file=file)
    print(f"revenue: posted weekly report ({rep['active']} units)")
    log_event("report", f"تقرير الإيرادات الأسبوعي · {rep['active']} وحدة")

_revenue_last_date = None

@tasks.loop(minutes=30)
async def revenue_loop():
    """Fire once on the configured weekday + hour (Riyadh)."""
    global _revenue_last_date
    now = datetime.now(TZ)
    if now.weekday() != REVENUE_REPORT_DOW or now.hour != REVENUE_REPORT_HOUR:
        return
    if _revenue_last_date == now.date():
        return
    _revenue_last_date = now.date()
    try:
        await post_revenue_report()
    except Exception as e:
        print("revenue_loop error:", e)

# ==================== Per-date pricing opportunities + last-week review ====================
_res_cache = {"data": None, "ts": 0}

def get_reservations_cached(ttl=1800):
    """Cache the full reservation pull so multiple reports in a short window reuse it."""
    if _res_cache["data"] is not None and (time.time() - _res_cache["ts"]) < ttl:
        return _res_cache["data"]
    data = fetch_all_reservations()
    _res_cache["data"], _res_cache["ts"] = data, time.time()
    return data

def fetch_calendar_days(listing_id, start, end):
    try:
        data = api_get(f"/listings/{listing_id}/calendar",
                       params={"startDate": start.isoformat(), "endDate": end.isoformat()})
        return data.get("result", []) or []
    except Exception as e:
        print(f"calendar fetch error ({listing_id}):", e)
        return []

def compute_demand_factors(reservations):
    """Build pricing multipliers from real history: per-unit achieved ADR + month / day-of-month
    / day-of-week demand indices (all relative to the portfolio average)."""
    today = datetime.now(TZ).date()
    y_start = today - timedelta(days=365)
    nights, arrivals = _explode_nights(reservations)
    u_rev, u_n = defaultdict(float), defaultdict(int)
    m_rev, m_n = defaultdict(float), defaultdict(int)
    w_rev, w_n = defaultdict(float), defaultdict(int)
    for lid, d, nightly in nights:
        u_rev[lid] += nightly
        u_n[lid] += 1
        m_rev[d.month] += nightly
        m_n[d.month] += 1
        w_rev[d.weekday()] += nightly
        w_n[d.weekday()] += 1
    unit_adr = {lid: (u_rev[lid] / u_n[lid]) for lid in u_n if u_n[lid]}
    tot_n = sum(u_n.values())
    overall = (sum(u_rev.values()) / tot_n) if tot_n else 0
    month_index = {m: ((m_rev[m] / m_n[m]) / overall if overall and m_n[m] else 1) for m in range(1, 13)}
    dow_index = {w: ((w_rev[w] / w_n[w]) / overall if overall and w_n[w] else 1) for w in range(7)}
    occ_count = defaultdict(int)
    dd = y_start
    while dd < today:
        occ_count[dd.day] += 1
        dd += timedelta(days=1)
    arr = defaultdict(int)
    for lid, ci in arrivals:
        if y_start <= ci < today:
            arr[ci.day] += 1
    denom = sum(occ_count[d] for d in range(1, 32) if occ_count.get(d))
    mean = (sum(arr.values()) / denom) if denom else 0
    dom_index = {d: ((arr[d] / occ_count[d]) / mean if mean and occ_count.get(d) else 1)
                 for d in range(1, 32)}
    return {"unit_adr": unit_adr, "overall_adr": overall, "month_index": month_index,
            "dow_index": dow_index, "dom_index": dom_index, "unit_nights": dict(u_n)}

def compute_price_opportunities(factors, units, horizon=None):
    """For each active unit's UNBOOKED future nights, compute a demand-informed target price
    and compare to the current calendar price. Returns (per_unit, all_rows)."""
    horizon = horizon or PRICE_OPP_HORIZON
    today = datetime.now(TZ).date()
    end = today + timedelta(days=horizon)
    overall = factors["overall_adr"]
    per_unit = {}
    all_rows = []
    for u in units:
        lid, name = u.get("id"), u.get("name")
        if not lid:
            continue
        base = factors["unit_adr"].get(lid) or u.get("price") or overall
        if not base:
            continue
        pu = per_unit.setdefault(lid, {"name": name, "raise": [], "drop": [], "uplift": 0.0,
                                       "base": round(base), "n_hist": factors.get("unit_nights", {}).get(lid, 0),
                                       "checked": 0, "gap_sum": 0.0})
        for day in fetch_calendar_days(lid, today, end):
            d = _parse_date(day.get("date"))
            if not d:
                continue
            available = int(day.get("isAvailable", 0) or 0) == 1 and not day.get("reservationId")
            if not available:
                continue                                   # booked/blocked -> can't reprice
            pu["checked"] += 1
            cur = day.get("price")
            cur = float(cur) if isinstance(cur, (int, float)) and cur > 0 else None
            mi = factors["month_index"].get(d.month, 1)
            di = factors["dom_index"].get(d.day, 1)
            wi = factors["dow_index"].get(d.weekday(), 1)
            target = max(0.6 * base, min(1.8 * base, base * mi * di * wi))
            lead = (d - today).days
            clear = target * (0.88 if lead <= 7 else (0.95 if lead <= 14 else 1.0))
            row = {"lid": lid, "name": name, "date": d.isoformat(), "wd": d.weekday(),
                   "current": round(cur) if cur else None, "target": round(target),
                   "clear": round(clear), "lead": lead, "reco": "ok"}
            if cur and cur < 0.90 * target:
                row["reco"] = "raise"
                pu["uplift"] += (target - cur)
                pu["gap_sum"] += (target - cur) / cur
                pu["raise"].append(row)
            elif cur and lead <= 10 and cur > 1.12 * clear:
                row["reco"] = "drop"
                pu["drop"].append(row)
            all_rows.append(row)
    # ---- neutral confidence score per unit (data volume + signal strength + corroboration) ----
    for pu in per_unit.values():
        nr, nd = len(pu["raise"]), len(pu["drop"])
        avg_gap = (pu["gap_sum"] / nr) if nr else 0.0          # average price gap (fraction)
        data_conf = min(1.0, pu["n_hist"] / 60.0)             # 60+ nights of history saturates
        signal_conf = max(min(1.0, avg_gap / 0.30), 0.6 if nd else 0.0)
        count_conf = min(1.0, (nr + nd) / 12.0)
        conf = 100 * (0.45 * data_conf + 0.35 * signal_conf + 0.20 * count_conf)
        pu["confidence"] = int(max(40, min(90, round(conf))))
        pu["avg_gap"] = avg_gap
    return per_unit, all_rows

_AR_WD = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

# pending price-change cards: discord_message_id -> {listing_id, name, changes:[{date,price,kind}]}
_price_opps = {}

def apply_price_changes(listing_id, changes):
    """Write the approved nightly prices to the Hostaway calendar. Re-verifies the dates are
    still available first (one range read), then PUTs each. Honors PRICE_APPLY_DRYRUN.
    Returns (applied, skipped, results) where results = [{date, kind, price, status}]."""
    if not changes:
        return (0, 0, [])
    dates = sorted(d for d in (_parse_date(c["date"]) for c in changes) if d)
    available = set()
    try:
        cal = api_get(f"/listings/{listing_id}/calendar",
                      params={"startDate": dates[0].isoformat(), "endDate": dates[-1].isoformat()})
        for day in (cal.get("result") or []):
            if int(day.get("isAvailable", 0) or 0) == 1 and not day.get("reservationId"):
                dd = _parse_date(day.get("date"))
                if dd:
                    available.add(dd.isoformat())
    except Exception as e:
        print("price re-verify error:", e)
        available = None                       # couldn't verify -> best effort, apply anyway
    applied, skipped, results = 0, 0, []
    for c in changes:
        price = int(round(c["price"]))
        if available is not None and c["date"] not in available:
            skipped += 1                        # got booked / blocked since the report
            results.append({"date": c["date"], "kind": c.get("kind"), "price": price, "status": "booked"})
            continue
        if PRICE_APPLY_DRYRUN:
            print(f"[DRY-RUN] would set {listing_id} {c['date']} -> {price} ر.س")
            applied += 1
            results.append({"date": c["date"], "kind": c.get("kind"), "price": price, "status": "dry"})
            continue
        try:
            api_put(f"/listings/{listing_id}/calendar",
                    {"startDate": c["date"], "endDate": c["date"],
                     "isAvailable": 1, "price": price,
                     "note": f"ouja-orig:{price}"})   # anchor for the discount tiers later
            applied += 1
            results.append({"date": c["date"], "kind": c.get("kind"), "price": price, "status": "applied"})
        except Exception as e:
            print(f"apply price error ({listing_id} {c['date']}):", e)
            skipped += 1
            results.append({"date": c["date"], "kind": c.get("kind"), "price": price, "status": "error"})
    return applied, skipped, results

def _unit_changes(pu):
    """Flatten a unit's raise/drop rows into apply-ready change dicts."""
    out = []
    for r in pu["raise"]:
        out.append({"date": r["date"], "price": r["target"], "kind": "raise"})
    for r in pu["drop"]:
        out.append({"date": r["date"], "price": r["clear"], "kind": "drop"})
    return out

def build_price_opp_summary(per_unit, all_rows):
    total_uplift = round(sum(p["uplift"] for p in per_unit.values()))
    n_raise = sum(len(p["raise"]) for p in per_unit.values())
    n_drop = sum(len(p["drop"]) for p in per_unit.values())
    e = discord.Embed(
        title="💰 فرص التسعير لكل ليلة · عوجا",
        description=(f"فحصت الليالي المتاحة للـ{PRICE_OPP_HORIZON} يوم الجاية.\n"
                     f"🔼 ليالي ناقصة تسعير: **{n_raise}** · 🔽 ليالي قريبة تحتاج تخفيض لتمتلئ: **{n_drop}**\n"
                     f"💵 إيراد إضافي تقديري لو رفعت الناقصة: **~{total_uplift} ر.س**\n"
                     f"تحت تلقى بطاقة لكل وحدة — اضغط **✅ طبّق** عشان أغيّر الأسعار فعلياً، أو **❌ تجاهل**."
                     + ("\n⚠️ **وضع التجربة (DRY-RUN)** شغّال — ما راح يتغيّر شي فعلي."
                        if PRICE_APPLY_DRYRUN else "")),
        color=GOLD)
    out = ["unit,date,weekday,current_SAR,target_SAR,clearing_SAR,lead_days,reco"]
    for r in all_rows:
        if r["reco"] == "ok":
            continue
        out.append(",".join(['"' + str(r["name"]).replace('"', "'") + '"', r["date"],
                              str(r["wd"]), str(r["current"] or ""), str(r["target"]),
                              str(r["clear"]), str(r["lead"]), r["reco"]]))
    return e, ("\n".join(out)).encode("utf-8-sig")

def _conf_bar(pct):
    filled = round(pct / 10)
    return "█" * filled + "░" * (10 - filled)

def build_unit_card(pu):
    """An embed for one unit's opportunities (shown with Apply/Skip buttons)."""
    nr, nd = len(pu["raise"]), len(pu["drop"])
    conf = pu.get("confidence", 50)
    desc = []
    if nr:
        desc.append(f"🔼 **رفع {nr} ليلة** (إيراد إضافي ~{round(pu['uplift'])} ر.س)")
    if nd:
        desc.append(f"🔽 **خفض {nd} ليلة** (ليالي قريبة فاضية، عشان تمتلئ)")
    e = discord.Embed(title=str(pu["name"])[:256], description="\n".join(desc), color=GOLD)
    lines = []
    for r in sorted(pu["raise"], key=lambda x: (x["target"] - (x["current"] or 0)), reverse=True)[:8]:
        lines.append(f"🔼 {r['date']} ({_AR_WD[r['wd']]}): {r['current']} → ~{r['target']} ر.س")
    if nr > 8:
        lines.append(f"… +{nr-8} ليالي رفع أخرى")
    for r in sorted(pu["drop"], key=lambda x: x["lead"])[:5]:
        lines.append(f"🔽 {r['date']} ({_AR_WD[r['wd']]}, بعد {r['lead']} يوم): {r['current']} → ~{r['clear']} ر.س")
    if nd > 5:
        lines.append(f"… +{nd-5} ليالي خفض أخرى")
    if lines:
        e.add_field(name="التفاصيل", value="\n".join(lines)[:1024], inline=False)
    # ---- neutral "why" / facts ----
    facts = [f"• متوسط سعرك الفعلي تاريخياً: ~{pu.get('base', 0)} ر.س",
             f"• فحصت {pu.get('checked', 0)} ليلة متاحة في الـ{PRICE_OPP_HORIZON} يوم الجاية"]
    if nr:
        facts.append(f"• {nr} ليلة سعرها الحالي أقل من المتوقّع (فرق متوسط +{round(pu.get('avg_gap',0)*100)}%)")
    if nd:
        facts.append(f"• {nd} ليلة قريبة لا زالت فاضية وسعرها أعلى من سعر التصريف")
    facts.append("• الأساس: متوسط سعر وحدتك × الشهر × اليوم بالشهر × يوم الأسبوع — من بياناتك أنت")
    e.add_field(name="📊 ليه؟ (حقائق)", value="\n".join(facts)[:1024], inline=False)
    e.add_field(name="🎯 نسبة الثقة في التوصية",
                value=f"`{_conf_bar(conf)}` **{conf}%**\nمحسوبة من حجم بياناتك + قوة فرق السعر — مو ضمان بيع.",
                inline=False)
    e.set_footer(text="✅ طبّق = أغيّر هالأسعار في تقويمك · الأسعار قبل الضريبة ورسوم المنصة")
    return e

async def post_price_opportunities():
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return
    channel = await ensure_channel(guild, PRICE_OPP_CHANNEL, await get_assistant_category(guild))
    if channel is None:
        return
    if not _catalog_units:
        await asyncio.to_thread(load_catalog, True)
    reservations = await asyncio.to_thread(get_reservations_cached)
    if not reservations or not _catalog_units:
        await channel.send("⚠️ ما قدرت أجهّز فرص التسعير — بيانات الحجوزات أو قائمة الوحدات ناقصة.")
        return
    factors = await asyncio.to_thread(compute_demand_factors, reservations)
    per_unit, rows = await asyncio.to_thread(compute_price_opportunities, factors, _catalog_units)
    summary, csv_bytes = build_price_opp_summary(per_unit, rows)
    file = discord.File(io.BytesIO(csv_bytes), filename="ouja_price_opportunities.csv")
    await channel.send(embed=summary, file=file)
    # one action card per unit (top by uplift), each with Apply/Skip buttons
    ranked = sorted([p for p in per_unit.values() if p["raise"] or p["drop"]],
                    key=lambda p: p["uplift"], reverse=True)
    posted = 0
    for pu in ranked[:PRICE_OPP_MAX_CARDS]:
        changes = _unit_changes(pu)
        if not changes:
            continue
        msg = await channel.send(embed=build_unit_card(pu), view=PriceApplyView())
        _price_opps[msg.id] = {"listing_id": pu["lid"], "name": pu["name"], "changes": changes}
        posted += 1
    print(f"price-opp: posted summary + {posted} action cards ({len(per_unit)} units checked)")
    log_event("pricing", f"فرص التسعير · {posted} بطاقة وحدة")

def compute_last_week(reservations, listings_map, factors):
    """Actual performance of the last 7 days vs the prior 7, per unit + portfolio."""
    today = datetime.now(TZ).date()
    w0, wp = today - timedelta(days=7), today - timedelta(days=14)
    nights, _ = _explode_nights(reservations)
    cur = defaultdict(lambda: {"n": 0, "rev": 0.0})
    prev = defaultdict(lambda: {"n": 0, "rev": 0.0})
    for lid, d, nightly in nights:
        if w0 <= d < today:
            cur[lid]["n"] += 1
            cur[lid]["rev"] += nightly
        elif wp <= d < w0:
            prev[lid]["n"] += 1
            prev[lid]["rev"] += nightly
    lids = set(list(cur) + list(prev) + [u["id"] for u in _catalog_units if u.get("id")])
    units = []
    for lid in lids:
        n, rev = cur[lid]["n"], cur[lid]["rev"]
        adr = (rev / n) if n else (factors["unit_adr"].get(lid) or factors["overall_adr"])
        empty = max(0, 7 - n)
        missed = empty * (adr or 0)
        units.append({"lid": lid, "name": listings_map.get(lid) or f"unit-{lid}",
                      "n": n, "rev": rev, "occ": n / 7, "adr": adr, "empty": empty,
                      "missed": missed, "prev_n": prev[lid]["n"], "prev_rev": prev[lid]["rev"]})
    tot_rev = sum(u["rev"] for u in units)
    tot_n = sum(u["n"] for u in units)
    tot_prev = sum(u["prev_rev"] for u in units)
    avail = len(units) * 7
    return {"units": units, "tot_rev": tot_rev, "tot_nights": tot_n,
            "occ": (tot_n / avail) if avail else 0, "tot_prev": tot_prev,
            "tot_missed": sum(u["missed"] for u in units), "w0": w0, "today": today}

def build_last_week_message(rep):
    delta = rep["tot_rev"] - rep["tot_prev"]
    arrow = "🟢▲" if delta >= 0 else "🔴▼"
    pct = (round(delta / rep["tot_prev"] * 100) if rep["tot_prev"] else 0)
    e = discord.Embed(
        title="📅 مراجعة الأسبوع الماضي · عوجا",
        description=(f"من {rep['w0']} إلى {rep['today']}\n"
                     f"الإيراد: **{round(rep['tot_rev'])} ر.س**  {arrow} {pct:+d}% عن الأسبوع قبله\n"
                     f"الإشغال: **{round(rep['occ']*100)}%** · ليالي مباعة: **{rep['tot_nights']}**\n"
                     f"💸 إيراد ضائع تقديري من الليالي الفاضية: **~{round(rep['tot_missed'])} ر.س**"),
        color=GOLD)
    worst = sorted([u for u in rep["units"] if u["empty"] > 0],
                   key=lambda u: u["missed"], reverse=True)[:8]
    if worst:
        e.add_field(
            name="أكثر وحدات فيها ليالي فاضية (فرصة ضائعة)",
            value="\n".join(f"• **{u['name']}**: {u['empty']} ليالي فاضية · "
                            f"~{round(u['missed'])} ر.س ضائعة · إشغال {round(u['occ']*100)}%"
                            for u in worst)[:1024],
            inline=False)
    best = sorted(rep["units"], key=lambda u: u["rev"], reverse=True)[:5]
    if best and best[0]["rev"]:
        e.add_field(name="الأعلى إيراداً هالأسبوع",
                    value="\n".join(f"• **{u['name']}**: {round(u['rev'])} ر.س · "
                                    f"إشغال {round(u['occ']*100)}%" for u in best if u["rev"])[:1024],
                    inline=False)
    e.set_footer(text="«الإيراد الضائع» = ليالي فاضية × متوسط سعر الوحدة · تقديري")
    return e

async def post_last_week_review():
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return
    channel = await ensure_channel(guild, WEEKLY_REVIEW_CHANNEL, await get_assistant_category(guild))
    if channel is None:
        return
    if not _catalog_units:
        await asyncio.to_thread(load_catalog, True)
    reservations = await asyncio.to_thread(get_reservations_cached)
    if not reservations:
        await channel.send("⚠️ ما قدرت أجيب بيانات الحجوزات لمراجعة الأسبوع.")
        return
    listings_map = await asyncio.to_thread(get_listings_map)
    factors = await asyncio.to_thread(compute_demand_factors, reservations)
    rep = await asyncio.to_thread(compute_last_week, reservations, listings_map, factors)
    await channel.send(embed=build_last_week_message(rep))
    print("last-week-review: posted")
    log_event("report", "مراجعة الأسبوع الماضي")

_price_opp_last = None
_review_last = None

@tasks.loop(minutes=30)
async def price_opp_loop():
    global _price_opp_last
    now = datetime.now(TZ)
    if now.weekday() != PRICE_OPP_DOW or now.hour != PRICE_OPP_HOUR or _price_opp_last == now.date():
        return
    _price_opp_last = now.date()
    try:
        await post_price_opportunities()
    except Exception as e:
        print("price_opp_loop error:", e)

@tasks.loop(minutes=30)
async def weekly_review_loop():
    global _review_last
    now = datetime.now(TZ)
    if now.weekday() != WEEKLY_REVIEW_DOW or now.hour != WEEKLY_REVIEW_HOUR or _review_last == now.date():
        return
    _review_last = now.date()
    try:
        await post_last_week_review()
    except Exception as e:
        print("weekly_review_loop error:", e)


@bot.event
async def on_ready():
    load_state()                       # restore seen/cards/escalations from the volume FIRST
    bot.add_view(CleaningDoneView())   # re-bind button handlers after a restart
    bot.add_view(ClaimView())          # re-bind escalation claim buttons after a restart
    bot.add_view(ApproveView())        # re-bind guest-reply approval buttons after a restart
    bot.add_view(PriceApplyView())     # re-bind price apply/skip buttons after a restart
    # On the FIRST start only (no saved state yet), mark the whole current inbox as
    # already-seen so we never replay old backlog. After this, ONLY genuinely new message
    # IDs get a card — and persistence keeps _assistant_seen across restarts, so redeploys
    # don't re-baseline and don't miss messages that arrive during a restart.
    # (No timestamp guessing here — that was reading Hostaway times in the wrong timezone
    #  and making fresh messages look hours old, which replayed old chats and skipped new ones.)
    if ASSISTANT_ENABLED and not ASSISTANT_TEST and not _assistant_seen:
        try:
            base = await asyncio.to_thread(fetch_new_guest_messages, set(), False)
            for it in base:
                _assistant_seen.add(it["message_id"])
            await asyncio.to_thread(persist_state)   # save immediately so it survives a restart
            print(f"assistant: baselined {len(_assistant_seen)} existing conversations "
                  f"— from now on only NEW messages get cards")
        except Exception as e:
            print("assistant baseline error:", e)
    print(f"Logged in as {bot.user}. Watching for checkouts every {POLL_MINUTES} min.")
    print(f"Weekday tiers (Riyadh): {DISCOUNT_TIER1_PERCENT:.0f}% at {DISCOUNT_TIER1_HOUR:02d}:00, "
          f"{DISCOUNT_TIER2_PERCENT:.0f}% at {DISCOUNT_TIER2_HOUR:02d}:00, "
          f"{DISCOUNT_TIER3_PERCENT:.0f}% at {DISCOUNT_TIER3_HOUR:02d}:00 "
          f"{'(DRY-RUN)' if DISCOUNT_DRY_RUN else '(LIVE)'}")
    print(f"Weekend rule (Thu/Fri): {WEEKEND_DISCOUNT_PERCENT:.0f}% at "
          f"{WEEKEND_DISCOUNT_HOUR:02d}:{WEEKEND_DISCOUNT_MINUTE:02d} only")
    print(f"Heads-up preview at {HEADS_UP_HOUR:02d}:00 -> #{HEADS_UP_CHANNEL}")
    print(f"Cleaning reminders: every {REMINDER_SLOW_MIN} min "
          f"{REMINDER_START_HOUR:02d}:00–{REMINDER_FAST_HOUR:02d}:00, then every "
          f"{REMINDER_FAST_MIN} min until {REMINDER_END_HOUR:02d}:00")
    print(f"AI assistant: {'ON' if ASSISTANT_ENABLED else 'OFF'} · model={CLAUDE_MODEL} · "
          f"premium={CLAUDE_MODEL_PREMIUM} · "
          f"auto-send simple={'ON' if ASSISTANT_AUTO else 'OFF'} · "
          f"escalation-ack={'ON' if ASSISTANT_ESC_ACK else 'OFF'} -> #{ASSISTANT_CHANNEL}")
    if not poll_loop.is_running():
        poll_loop.start()
    if not reminder_loop.is_running():
        reminder_loop.start()
    if not discount_tier1_loop.is_running():
        discount_tier1_loop.start()
    if not discount_tier2_loop.is_running():
        discount_tier2_loop.start()
    if not discount_tier3_loop.is_running():
        discount_tier3_loop.start()
    if not discount_weekend_loop.is_running():
        discount_weekend_loop.start()
    if not headsup_loop.is_running():
        headsup_loop.start()
    if ASSISTANT_ENABLED:
        guild0 = bot.get_guild(GUILD_ID)
        if guild0 is not None:
            await load_knowledge(guild0)
            try:                                   # make the auto-reply audit room exist up front
                cat = await get_assistant_category(guild0)
                ch = await ensure_channel(guild0, AUTO_REPLY_CHANNEL, cat)
                if ch is not None and not [m async for m in ch.history(limit=1)]:
                    note = ("📝 **سجل الردود التلقائية** — كل رد يرسله المساعد فيصل تلقائياً بيتسجّل هنا.\n"
                            f"التشغيل التلقائي الحين: **{'مفعّل ✅' if ASSISTANT_AUTO else 'متوقف — فعّله بـ ASSISTANT_AUTO=1'}**"
                            if not ASSISTANT_AUTO else
                            "📝 **سجل الردود التلقائية** — كل رد يرسله المساعد فيصل تلقائياً بيتسجّل هنا.")
                    await ch.send(note)
            except Exception as e:
                print("auto-reply room setup:", e)
        await asyncio.to_thread(load_catalog, True)
    if not assistant_loop.is_running():
        assistant_loop.start()
    if not escalation_reping_loop.is_running():
        escalation_reping_loop.start()
    if not persist_loop.is_running():
        persist_loop.start()
    if DASHBOARD_ENABLED and DASHBOARD_TOKEN and not dashboard_cache_loop.is_running():
        dashboard_cache_loop.start()   # warms the cache immediately, then every few minutes
    if PRICING_STRATEGY_ENABLED and not pricing_strategy_loop.is_running():
        pricing_strategy_loop.start()
    if not revenue_loop.is_running():
        revenue_loop.start()
    if not price_opp_loop.is_running():
        price_opp_loop.start()
    if not weekly_review_loop.is_running():
        weekly_review_loop.start()
    if WEBHOOKS_ENABLED and _HAS_AIOHTTP and _web_runner is None:
        try:
            await start_web_server()
        except Exception as e:
            print("web server start error:", e)
    elif WEBHOOKS_ENABLED and not _HAS_AIOHTTP:
        print("webhooks: aiohttp not installed — add 'aiohttp' to requirements.txt to enable")
    if ASSISTANT_ENABLED and not knowledge_loop.is_running():
        knowledge_loop.start()
    if HEADS_UP_TEST:
        print("HEADS_UP_TEST=1 — posting a heads-up preview now (test run)")
        try:
            items, tomorrow, weekend = await asyncio.to_thread(compute_headsup)
            await post_headsup(items, tomorrow, weekend)
        except Exception as e:
            print("test heads-up error:", e)
    if REVENUE_TEST:
        print("REVENUE_TEST=1 — building the weekly revenue report now (test run)")
        try:
            await post_revenue_report()
        except Exception as e:
            print("test revenue report error:", e)
    if PRICE_OPP_TEST:
        print("PRICE_OPP_TEST=1 — building price opportunities now (test run)")
        try:
            await post_price_opportunities()
        except Exception as e:
            print("test price-opp error:", e)
    if WEEKLY_REVIEW_TEST:
        print("WEEKLY_REVIEW_TEST=1 — building last-week review now (test run)")
        try:
            await post_last_week_review()
        except Exception as e:
            print("test last-week-review error:", e)
    if DISCOUNT_TEST not in ("0", "", "false", "False", "no"):
        try:
            pct = (DISCOUNT_TIER1_PERCENT if DISCOUNT_TEST in ("1", "true", "True", "yes")
                   else float(DISCOUNT_TEST))
        except ValueError:
            pct = DISCOUNT_TIER1_PERCENT
        print(f"DISCOUNT_TEST — running a {pct:.0f}% tier now "
              f"({'DRY-RUN' if DISCOUNT_DRY_RUN else 'LIVE'})")
        await _run_tier(pct, "Test (startup)")

if __name__ == "__main__":
    missing = [k for k in ("HOSTAWAY_ACCOUNT_ID", "HOSTAWAY_API_KEY", "DISCORD_TOKEN", "DISCORD_GUILD_ID")
               if not os.environ.get(k)]
    if missing:
        raise SystemExit("Missing environment variables: " + ", ".join(missing))
    bot.run(DISCORD_TOKEN)
