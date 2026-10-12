# -*- coding: utf-8 -*-
"""
site_home/ — the oujares.com company homepage + legal pages (business.sa e-commerce
verification, 2026-10-12).

  /  /en                      company homepage (identity card, licences, links)
  /privacy  /en/privacy        privacy policy (PDPL)
  /terms    /en/terms          terms and conditions
  /contact  /en/contact        contact + 24/7 complaints

The company's official details live in ONE dict, identity.SITE_IDENTITY. bot.py calls
site_home.wire({...}) then site_home.register_routes(app).
"""
from .host import HOST, wire as _wire_host
from .identity import SITE_IDENTITY
from . import content, render, routes  # noqa: F401

__all__ = ["wire", "register_routes", "site_paths", "SITE_IDENTITY", "HOST"]


def wire(caps):
    _wire_host(caps)
    render.set_fallbacks(email=HOST.email, whatsapp=HOST.whatsapp)
    return HOST


def register_routes(app):
    routes.register(app)


def site_paths():
    return routes.site_paths()
