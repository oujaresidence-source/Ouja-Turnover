# -*- coding: utf-8 -*-
"""
owner_report — Ouja Owner Performance Report module.

An isolated, read-only-against-Hostaway pipeline that turns Hostaway data plus
gated operator answers into a validated, provenance-tagged `cfg` dict, renders it
through the FROZEN renderer (`owner_report/renderer/ouja_render.py`), and writes an
immutable audit snapshot per `doc_ref`.

The renderer owns 100% of the visual output and must never be edited. This package
owns only the data pipeline that produces the `cfg` the renderer consumes.

Public surface:
    from owner_report import build_report, BuildError
    build_report(inputs, out_pdf_path)      # runs model -> validate -> audit_layout -> render -> snapshot
"""

from .provenance import Fig, ProvenanceError, VALID_TAGS
from .errors import BuildError, ValidationError
from .host import HOST, wire as _wire_host
from . import host, live, routes, page, questions  # noqa: F401  (pure; no renderer at import)


def wire(caps):
    """bot.py calls this once at web-server start with the READ-only caps."""
    _wire_host(caps)
    return HOST


def register_routes(app):
    routes.register(app)


def build_report(*args, **kwargs):
    """Lazy proxy to build.build_report (build.py imports the renderer; keep import lazy
    so pure-logic consumers/tests don't pull Playwright on older interpreters)."""
    from .build import build_report as _impl
    return _impl(*args, **kwargs)


def reconciliation(cfg):
    from .build import reconciliation as _impl
    return _impl(cfg)


__all__ = [
    "Fig", "ProvenanceError", "VALID_TAGS", "BuildError", "ValidationError",
    "build_report", "reconciliation", "wire", "register_routes", "HOST",
]
