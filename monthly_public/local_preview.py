"""Localhost-only, read-only server for visual monthly customer-journey QA."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, Mapping
from zoneinfo import ZoneInfo

from .page import CSS_PATH, JS_PATH, render_monthly_page
from .preview import build_preview_app
from .priority_places import load_priority_places


LOCAL_HOST = "127.0.0.1"
DEFAULT_TOKEN = "ouja-local-preview"

_ROUTES = (
    ("GET", "/monthly/ops/preview"),
    ("GET", "/monthly/ops/preview/search"),
    ("GET", "/monthly/ops/preview/match"),
    ("GET", "/monthly/ops/preview/id/{lid}"),
    ("GET", "/monthly/ops/preview/{slug}"),
    ("GET", "/api/monthly/ops/preview/config"),
    ("GET", "/api/monthly/ops/preview/search"),
    ("POST", "/api/monthly/ops/preview/match"),
    ("GET", "/api/monthly/ops/preview/listing/{id}"),
)


def route_contract() -> tuple[tuple[str, str], ...]:
    """Return the intentionally narrow local surface for safety tests."""

    return _ROUTES


def _text(value: Any) -> Any:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _numbers(value: Any) -> Any:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _public_listing(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """Allowlist only fields already returned by Ouja's public stay catalog."""

    listing_id = str(raw.get("id") or "").strip()
    if not listing_id:
        raise ValueError("public catalog row has no listing id")
    images = [
        value for value in (raw.get("images") or ())
        if isinstance(value, str) and value.startswith("https://")
    ]
    amenities = [
        value.strip() for value in (raw.get("amenities") or ())
        if isinstance(value, str) and value.strip()
    ]
    facts = raw.get("facts") if isinstance(raw.get("facts"), Mapping) else {}
    rating = _numbers(raw.get("rating"))
    reviews_count = _numbers(raw.get("reviews_count"))
    rating_verified = rating is not None and reviews_count is not None
    structured = (
        copy.deepcopy(dict(raw["structured"]))
        if isinstance(raw.get("structured"), Mapping)
        else None
    )
    return {
        "id": raw.get("id"),
        "active": True,
        "slug": _text(raw.get("slug")),
        "name_ar": _text(raw.get("name_ar")),
        "name_en": _text(raw.get("name_en")),
        "short_ar": _text(raw.get("short_ar")),
        "short_en": _text(raw.get("short_en")),
        "structured": structured,
        "content_verified": structured is not None,
        "neighborhood": _text(raw.get("neighborhood")),
        "neighborhood_ar": None,
        "neighborhood_en": None,
        "neighborhood_verified": False,
        "bedrooms": _numbers(raw.get("bedrooms")),
        "beds": _numbers(raw.get("beds")),
        "beds_count": _numbers(raw.get("beds_count")),
        "baths": _numbers(raw.get("baths")),
        "capacity": _numbers(raw.get("capacity")),
        "floor_area_sqm": None,
        "images": images,
        "amenities": amenities,
        "facts": {
            str(key): value for key, value in facts.items()
            if isinstance(key, str) and isinstance(value, bool)
        },
        "rating": rating if rating_verified else None,
        "reviews_count": reviews_count if rating_verified else None,
        "rating_verified": rating_verified,
        # /api/stay/search exposes the already-aggregated approved review signal.
        "rating_source": "approved_public_reviews" if rating_verified else None,
        "licence": None,
        "official_prices": {},
        "calendar": None,
        "commercial_terms": None,
        "coordinates": None,
    }


def build_source(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Convert one downloaded public catalog response without guessing fields."""

    results = payload.get("results") if isinstance(payload, Mapping) else None
    if not isinstance(results, list) or not results:
        raise ValueError("public catalog response has no results")
    listings = []
    identifiers = set()
    for raw in results:
        if not isinstance(raw, Mapping):
            raise ValueError("public catalog contains a malformed row")
        listing = _public_listing(raw)
        listing_id = str(listing["id"])
        if listing_id in identifiers:
            raise ValueError("public catalog contains duplicate listing ids")
        identifiers.add(listing_id)
        listings.append(listing)
    return {
        "refresh_ok": True,
        "catalog_complete": True,
        "listings": listings,
        "source_timestamps": {"listings": dt.datetime.now(dt.timezone.utc).isoformat()},
    }


class _MemoryService:
    def __init__(self, source: Mapping[str, Any]) -> None:
        self._source = copy.deepcopy(dict(source))

    @staticmethod
    def approved_settings_values() -> Dict[str, Any]:
        return {}

    def preview_inventory(self) -> Dict[str, Any]:
        return copy.deepcopy(self._source)

    @staticmethod
    def approved_places() -> Dict[str, Dict[str, Any]]:
        return {
            str(row["id"]): {key: copy.deepcopy(value) for key, value in row.items() if key != "id"}
            for row in load_priority_places()
        }


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _browse_query(query: Mapping[str, str]) -> Dict[str, Any]:
    out = {
        key: query[key]
        for key in (
            "move_in", "move_out", "duration_months", "bedrooms", "residents",
            "neighborhood", "flexibility", "lang",
        )
        if query.get(key) not in (None, "")
    }
    if "duration_months" not in out and query.get("months"):
        out["duration_months"] = query["months"]
    if "residents" not in out and query.get("guests"):
        out["residents"] = query["guests"]
    if "bedrooms" not in out and query.get("beds") not in (None, "", "all"):
        out["bedrooms"] = 0 if query["beds"] == "studio" else query["beds"]
    return out


def _listing_query(query: Mapping[str, str], identifier: str) -> Dict[str, Any]:
    out: Dict[str, Any] = (
        {"slug": identifier} if query.get("lookup") == "slug"
        else {"listing_id": identifier}
    )
    for key in ("move_in", "move_out", "duration_months", "residents", "purpose", "lang"):
        if query.get(key) not in (None, ""):
            out[key] = query[key]
    if "duration_months" not in out and query.get("months"):
        out["duration_months"] = query["months"]
    return out


def create_web_app(source: Mapping[str, Any], token: str = DEFAULT_TOKEN) -> Any:
    """Create a localhost QA app with no save, approve, lead, event, or refresh route."""

    from aiohttp import web

    if not isinstance(token, str) or not token:
        raise ValueError("preview token is required")
    clock = lambda: dt.datetime.now(ZoneInfo("Asia/Riyadh"))
    preview = build_preview_app(_MemoryService(source), clock=clock)

    def response(value: Any, status: int = 200) -> Any:
        return web.json_response(
            _plain(value), status=status,
            dumps=lambda item: json.dumps(item, ensure_ascii=False, separators=(",", ":")),
            headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"},
        )

    @web.middleware
    async def safety(request: Any, handler: Any) -> Any:
        if request.path not in (CSS_PATH, JS_PATH) and request.query.get("token") != token:
            return response({"ok": False, "error": {"code": "unauthorized"}}, 401)
        result = await handler(request)
        result.headers["X-Content-Type-Options"] = "nosniff"
        result.headers["Referrer-Policy"] = "no-referrer"
        return result

    app = web.Application(middlewares=[safety])

    async def page(request: Any, route: str) -> Any:
        body = render_monthly_page(
            route,
            slug=request.match_info.get("slug"),
            listing_id=request.match_info.get("lid"),
            preview=True,
        )
        return web.Response(
            text=body, content_type="text/html",
            headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"},
        )

    async def css(_request: Any) -> Any:
        return web.FileResponse(Path(__file__).with_name("static") / "monthly.css")

    async def javascript(_request: Any) -> Any:
        return web.FileResponse(Path(__file__).with_name("static") / "monthly.js")

    async def config(request: Any) -> Any:
        return response(preview.config(request.query.get("lang", "ar")))

    async def browse(request: Any) -> Any:
        return response(preview.browse(_browse_query(request.query)))

    async def match(request: Any) -> Any:
        try:
            body = await request.json()
        except (json.JSONDecodeError, TypeError):
            return response({"ok": False, "error": {"code": "invalid_request"}}, 400)
        language = body.pop("lang", "ar") if isinstance(body, dict) else "ar"
        return response(preview.match(body, language))

    async def listing(request: Any) -> Any:
        return response(preview.listing(
            _listing_query(request.query, request.match_info.get("id", ""))
        ))

    app.router.add_get(CSS_PATH, css)
    app.router.add_get(JS_PATH, javascript)
    app.router.add_get("/monthly/ops/preview", lambda request: page(request, "home"))
    app.router.add_get("/monthly/ops/preview/search", lambda request: page(request, "browse"))
    app.router.add_get("/monthly/ops/preview/match", lambda request: page(request, "match"))
    app.router.add_get("/monthly/ops/preview/id/{lid}", lambda request: page(request, "listing"))
    app.router.add_get("/api/monthly/ops/preview/config", config)
    app.router.add_get("/api/monthly/ops/preview/search", browse)
    app.router.add_post("/api/monthly/ops/preview/match", match)
    app.router.add_get("/api/monthly/ops/preview/listing/{id}", listing)
    app.router.add_get("/monthly/ops/preview/{slug}", lambda request: page(request, "listing"))
    return app


def run(source_path: str, *, port: int = 8765, token: str = DEFAULT_TOKEN) -> None:
    """Serve the preview on loopback only; never expose it on the local network."""

    from aiohttp import web

    with open(source_path, encoding="utf-8") as handle:
        source = build_source(json.load(handle))
    web.run_app(create_web_app(source, token), host=LOCAL_HOST, port=port, print=None)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Ouja's read-only monthly preview")
    parser.add_argument("--source", required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--token", default=DEFAULT_TOKEN)
    args = parser.parse_args()
    run(args.source, port=args.port, token=args.token)


if __name__ == "__main__":
    main()


__all__ = ["LOCAL_HOST", "build_source", "create_web_app", "route_contract", "run"]
