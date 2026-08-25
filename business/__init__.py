# -*- coding: utf-8 -*-
"""
business/ — the public B2B company profile at /business (a data room, superprompt §0).

A pure metrics core (business.metrics.compute_metrics) is the single source of truth;
the nightly job (business.snapshot) refreshes metrics_snapshot.json; the server-rendered
EN/AR pages (business.page) render from it. bot.py calls business.wire({...}) then
business.register_routes(app), same DI pattern as schedule/.
"""
from .host import HOST, wire as _wire_host
from . import metrics, manual, snapshot, render, page, routes  # noqa: F401

__all__ = ["wire", "register_routes", "run_snapshot", "HOST",
           "metrics", "snapshot", "render", "page"]


def wire(caps):
    _wire_host(caps)
    return HOST


def register_routes(app):
    routes.register(app)


def run_snapshot(today=None):
    """Called by the nightly job in bot.py. Uses injected save_json when wired."""
    return snapshot.build_and_write(today=today, save_json=HOST.save_json)
