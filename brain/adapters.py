"""
brain.adapters — the handoff layer. The Brain decides; the adapter dispatches. The rest of
the system never cares which adapter is active.

Karzoum's CONFIRMED format: an AUDIENCE LIST ONLY — three columns Name, Phone, Tag. The
message text + image are set inside Karzoum's own composer (NOT per row), so the operator
pastes them from the /brain dashboard. We still log every exported recipient to contact_log
+ audit_log at export time (that's what the Governor counts against).

Phase 1: CsvExportAdapter is active (download the audience CSV). KarzoumAdapter is a stub
until Karzoum's push API is provided.
"""

import io
import csv
from . import settings
from .host import HOST
from .util import today_iso, now_iso

# Karzoum import = audience only. First name, E.164 phone, tier as the Tag.
CSV_COLUMNS = ["Name", "Phone", "Tag"]
_BOM = "﻿"        # UTF-8 BOM so Arabic names open correctly in Excel / Karzoum


def _row(p):
    return [p.get("first_name", ""), p.get("phone", ""), p.get("tier", "")]


def build_csv(package, campaign_code="rec"):
    """package -> (filename, csv_text_with_BOM). Audience only: Name, Phone, Tag."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLUMNS)
    for p in package:
        w.writerow(_row(p))
    code = (package[0].get("campaign_code") if package else None) or campaign_code or "rec"
    filename = "ouja_brain_audience_%s_%s.csv" % (code, today_iso().replace("-", ""))
    return filename, _BOM + buf.getvalue()


class SenderAdapter:
    name = "base"

    def deliver(self, package, rec_row):
        raise NotImplementedError


class CsvExportAdapter(SenderAdapter):
    name = "csv"

    def deliver(self, package, rec_row):
        code = rec_row["campaign_code"] if rec_row is not None else "rec"
        filename, text = build_csv(package, code)
        # Best-effort persist to the volume; the download route also rebuilds on demand,
        # so a failed write here is non-fatal.
        saved = None
        try:
            if HOST.state_path:
                path = HOST.state_path(filename)
                with open(path, "w", encoding="utf-8", newline="") as f:
                    f.write(text)
                saved = path
        except OSError:
            saved = None
        return {"ok": True, "filename": filename, "count": len(package),
                "columns": CSV_COLUMNS, "saved_path": saved, "csv_text": text,
                "generated_at": now_iso()}


class KarzoumAdapter(SenderAdapter):
    name = "karzoum"

    def deliver(self, package, rec_row):
        # Phase 2: POST the Name/Phone/Tag audience to Karzoum's API. Inert until configured.
        return {"ok": False, "error": "karzoum_not_configured",
                "detail": "KarzoumAdapter is a stub until the push API spec is provided.",
                "count": len(package)}


_REGISTRY = {"csv": CsvExportAdapter(), "karzoum": KarzoumAdapter()}


def get_active():
    name = settings.get("active_sender_adapter") or "csv"
    adapter = _REGISTRY.get(name, _REGISTRY["csv"])
    # Never silently go live: if 'karzoum' is selected but still a stub, fall back to CSV.
    if adapter.name == "karzoum":
        return _REGISTRY["csv"]
    return adapter
