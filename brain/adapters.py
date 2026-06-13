"""
brain.adapters — the handoff layer. The Brain decides; the adapter dispatches. The rest of
the system never cares which adapter is active.

Phase 1: CsvExportAdapter is active — Approve produces a downloadable CSV package for
manual upload. KarzoumAdapter is a stub until Faisal sends Karzoum's API details.

CSV COLUMNS ARE PROVISIONAL. Faisal chose "wait for Karzoum's spec", so the exact column
names/order below are a sensible default and live in ONE place (CSV_COLUMNS); when the real
importer format arrives, edit that list and the field mapping in _row() — nothing else.
"""

import io
import csv
from . import settings
from .host import HOST
from .util import today_iso, now_iso

# Provisional — confirm against Karzoum's importer, then edit here only.
CSV_COLUMNS = ["first_name", "phone", "tier", "message", "media_url",
               "scheduled_time", "campaign_code", "member_id"]


def _row(p):
    return [p.get("first_name", ""), p.get("phone", ""), p.get("tier", ""),
            p.get("merged_message", ""), p.get("media_url", ""),
            p.get("scheduled_time", ""), p.get("campaign_code", ""), p.get("member_id", "")]


def build_csv(package):
    """package -> (filename, csv_text). Used by both deliver() and the download route."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLUMNS)
    for p in package:
        w.writerow(_row(p))
    code = package[0].get("campaign_code", "rec") if package else "rec"
    filename = "ouja_brain_%s_%s.csv" % (code, today_iso())
    return filename, buf.getvalue()


class SenderAdapter:
    name = "base"

    def deliver(self, package, rec_row):
        raise NotImplementedError


class CsvExportAdapter(SenderAdapter):
    name = "csv"

    def deliver(self, package, rec_row):
        filename, text = build_csv(package)
        # Best-effort persist to the volume so the file is retrievable; the download route
        # also rebuilds on demand, so a failed write here is non-fatal.
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
                "provisional_columns": True, "generated_at": now_iso()}


class KarzoumAdapter(SenderAdapter):
    name = "karzoum"

    def deliver(self, package, rec_row):
        # Phase 2: POST the package to Karzoum's API. Intentionally inert until configured.
        return {"ok": False, "error": "karzoum_not_configured",
                "detail": "KarzoumAdapter is a stub until the API spec is provided.",
                "count": len(package)}


_REGISTRY = {"csv": CsvExportAdapter(), "karzoum": KarzoumAdapter()}


def get_active():
    name = settings.get("active_sender_adapter") or "csv"
    # Never silently go live: if 'karzoum' is selected but it's still a stub, fall back to CSV.
    adapter = _REGISTRY.get(name, _REGISTRY["csv"])
    if adapter.name == "karzoum":
        return _REGISTRY["csv"]
    return adapter
