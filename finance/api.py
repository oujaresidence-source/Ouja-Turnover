# -*- coding: utf-8 -*-
"""Thin bridge between the ERP package and the live bot.py module.

`B` is bot.py's module object (set once by finance.mount). Everything the ERP
reuses from the monolith — auth, STATE_DIR stores, Daftra import, dup shield,
custody math, expenses V4, owner-report math — is reached as `B.<name>` so the
data layer stays single-sourced and untouched.
"""

import json

from aiohttp import web

B = None  # bot.py module object — set by finance.mount()


def attach(botmod):
    global B
    B = botmod


def jres(data, status=200):
    """JSON response that keeps Arabic readable (no \\uXXXX escapes)."""
    return web.json_response(
        data, status=status, dumps=lambda o: json.dumps(o, ensure_ascii=False))


def authed(request):
    """Same login the dashboard uses (DASHBOARD_TOKEN or session token)."""
    try:
        return bool(B and B._dash_auth(request))
    except Exception:
        return False


def can(request, tab, action="read"):
    """Role check via bot.py's _user_can (legacy token = super-admin)."""
    try:
        return bool(B and B._user_can(request, tab, action))
    except Exception:
        return False


def is_admin(request):
    """Admin = full-control role (approvals ≥3000, month close, migration)."""
    try:
        tok = request.query.get("token", "") or request.headers.get("X-Token", "")
        if B.DASHBOARD_TOKEN and B.hmac.compare_digest(tok, B.DASHBOARD_TOKEN):
            return True
        u = B._auth_session(request)
        return bool(u and u.get("role") == "admin")
    except Exception:
        return False
