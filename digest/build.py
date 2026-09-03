# -*- coding: utf-8 -*-
"""digest.build — the orchestrator: the ONLY module that sequences I/O.

collect (through the injected http / search) → confidence → verify links → rank +
alternates → voice polish → artwork → assemble the frozen payload → schema → re-verify
links right before render → guard → Chromium → files on disk → db rows. Nothing here
posts anywhere: Discord delivery lives in bot.py behind DIGEST_DRYRUN.

CLI (offline, from the saved fixtures, cold start):
    python3 -m digest.build --dry-run --week 2026-09-03 --fixtures
Live (network on, still no posting):
    python3 -m digest.build --dry-run"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime

from . import art, dates, db, links, rank, schema, voice
from .collect import base, elcinema, kooora, platinumlist, podcast, ratings, saff, search_secondary, verse, worth
from .host import HOST
from .render import build as render_build

MAX_REBUILDS = 3
EVENT_SEARCH_DOMAINS = ("webook.com", "visitsaudi.com", "spa.gov.sa", "riyadh.platinumlist.net")


class BuildError(RuntimeError):
    pass


# ---------------- the latch ----------------

def existing_week_of(now):
    row = db.issue_for_week(dates.week_for(now).iso)
    return row["week_of"] if row else None


def already_built(now):
    return existing_week_of(now) is not None


# ---------------- helpers ----------------

def _out_root(out_root):
    if out_root:
        return out_root
    try:
        return HOST.require("state_path")("digest")
    except Exception:
        return os.path.join(os.getcwd(), ".digest_out")


def _site_url(public_base):
    try:
        base_url = public_base() if callable(public_base) else (public_base or "")
    except Exception:
        base_url = ""
    return (base_url or "").rstrip("/")


def _fold_title(t):
    return voice.normalize(t or "").strip()


def _collect(week, now, http, search, load_json, report):
    """-> {section: [cand]} plus report['dropped'] / report['errors'] filled in."""
    by = {"events": [], "cinema": [], "worth": [], "fixtures": [], "podcast": []}

    def run(name, fn):
        try:
            return fn()
        except Exception as e:
            report["errors"].append("%s: %s: %s" % (name, type(e).__name__, e))
            report["dropped"].append({"ttl": name, "reason": "المصدر ما رد"})
            return None

    got = run("platinumlist", lambda: platinumlist.fetch(week, http, now))
    if got:
        cands, dropped, _ = got
        by["events"] += cands
        report["dropped"] += dropped
    if len(by["events"]) < 2 and search is not None:
        extra, _urls = run("search-events", lambda: search_secondary.run(
            "events", week, search, EVENT_SEARCH_DOMAINS, now,
            "فعاليات ومعارض عامة في الرياض لهذي الأيام (مو مؤتمرات)")) or ([], [])
        by["events"] += extra

    got = run("elcinema", lambda: elcinema.fetch(week, http, now))
    if got:
        cands, dropped, _ = got
        by["cinema"] += cands
        report["dropped"] += dropped

    got = run("saff", lambda: saff.fetch(week, http, now))
    events = []
    if got:
        fx, dropped, _ = got
        report["dropped"] += dropped
        kk = run("kooora", lambda: kooora.fetch(http))
        events = kk[0] if kk else []
        for f in fx:
            cc = kooora.cross_check(f, events) if events else None
            if cc is False:
                report["dropped"].append({"ttl": "%s – %s" % (f["home"], f["away"]), "reason": "المصدران ما اتفقوا على الموعد"})
                continue
            f["agreement"] = base.AGREE_YES if cc else base.AGREE_NO
            by["fixtures"].append(f)

    dataset = worth.load()
    try:
        override = load_json("digest_riyadh.json") if load_json else None
        if isinstance(override, dict) and isinstance(override.get("places"), list):
            dataset = override
    except Exception:
        pass
    resolved = {}
    if search is not None:
        for p in dataset.get("places") or []:
            if p.get("status") == "open" and not (p.get("url") or "").strip() and p.get("slug"):
                u = run("search-worth", lambda: search_secondary.resolve_place_url(p, search, worth.SEARCH_DOMAINS)) or ""
                if u:
                    resolved[p["slug"]] = u
    wc, w_ineligible = worth.candidates(week, now, dataset, resolved_urls=resolved)
    by["worth"] += wc
    report["ineligible_places"] = w_ineligible
    report["dataset"] = dataset

    got = run("podcast", lambda: podcast.fetch(week, http, now))
    if got:
        cands, dropped, _ = got
        by["podcast"] += cands
        report["dropped"] += dropped

    for section, cands in by.items():
        for c in cands:
            agreement = c.get("agreement", base.AGREE_NO)
            c["confidence"] = base.confidence(c.get("raw_conf", base.TIER_PRIMARY), agreement,
                                              (c.get("source") or {}).get("fetched_at"), now)
    return by


def _verify_and_prune(by, http, report, reason="الرابط ما يفتح"):
    urls = sorted({c.get("url", "") for cands in by.values() for c in cands if c.get("url")})
    ok = links.verify(urls, http)
    for section, cands in by.items():
        keep = []
        for c in cands:
            final = ok.get(c.get("url", ""))
            if not final:
                report["dropped"].append({"ttl": c.get("ttl") or ("%s – %s" % (c.get("home", ""), c.get("away", ""))), "reason": reason})
                continue
            c["url"] = final
            keep.append(c)
        by[section] = keep
    return set(ok.values())


def _polish(cands, model_call, model, seed=0):
    """Owner rule (2026-09-03): the sub is FACTS (day+date · place · price) built by the
    collectors and never rewritten. Only the numerals are normalised here; the model's
    one job is the section claim (see _claims)."""
    out = []
    for c in cands:
        if c.get("section") == "fixtures":
            out.append(c)
            continue
        d = dict(c)
        d["ttl"] = voice.prose_digits(d.get("ttl", ""))
        d["sub"] = voice.prose_digits(d.get("sub", ""))
        out.append(d)
    return out


def _claims(chosen, model_call, model, seed=0):
    """-> {section: claim} — '' when the model is absent or its line breaks a rule."""
    return {k: voice.polish_claim(k, v, model_call=model_call, model=model, seed=seed) for k, v in chosen.items() if v}


def _clean_enough(c):
    if c.get("section") == "fixtures":
        return True
    return voice.title_ok(c.get("ttl", "")) and voice.sub_ok(c.get("sub", "")) and voice.is_clean(c.get("ttl", "")) and voice.is_clean(c.get("sub", ""))


def _item_from(c, artinfo):
    """Candidate → schema item (only the keys the contract knows, plus the ones the
    renderer uses: venue / hook / ratings / logos / in_riyadh / stadium / kickoff)."""
    src = dict(c.get("source") or {})
    if c.get("section") == "fixtures":
        it = {"home": c["home"], "away": c["away"], "when": c["when"], "day": c["day"], "url": c["url"],
              "stadium": c.get("stadium", ""), "city": c.get("city", ""), "in_riyadh": bool(c.get("in_riyadh")),
              "kickoff_iso": c.get("kickoff_iso", ""), "source": src, "confidence": c["confidence"]}
        if artinfo and artinfo.get("kind") == "logos":
            it["logos"] = {"home": artinfo["home"], "away": artinfo["away"], "sha256": artinfo["sha256"]}
        return it
    art = {"kind": artinfo["kind"], "sha256": artinfo["sha256"], "src": artinfo["src"],
           "w": int(artinfo.get("w") or 0), "h": int(artinfo.get("h") or 0)}
    it = {"ttl": c["ttl"], "sub": c.get("sub", ""), "chip": c.get("chip") or "الرياض", "url": c["url"],
          "art": art, "day": c["day"], "source": src, "confidence": c["confidence"],
          "tags": dict(c.get("tags") or {}), "slug": c.get("slug"), "venue": c.get("venue", ""),
          "hook": c.get("hook", ""), "price": c.get("price_ar") or c.get("price", ""), "hours": c.get("hours", "")}
    if c.get("verified_on"):
        it["verified_on"] = c["verified_on"]
    if c.get("ratings"):
        it["ratings"] = c["ratings"]
    if c.get("imdb_id"):
        it["imdb_id"] = c["imdb_id"]
    return it


def _sayings():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sayings.json"), encoding="utf-8") as fh:
            return json.load(fh).get("sayings") or []
    except Exception:
        return []


def pick_saying(issue_no, sayings=None):
    items = sayings if sayings is not None else _sayings()
    if not items:
        return None
    s = items[(int(issue_no) - 1) % len(items)]
    return {"id": s.get("id"), "text": s.get("text"), "by": s.get("by", "")}


def pick_occasion(dataset, week, horizon_days=14):
    """A CONFIRMED calendar entry starting within `horizon_days` of the weekend."""
    from datetime import date, timedelta
    for c in (dataset or {}).get("calendar") or []:
        w = c.get("window")
        if not (c.get("confirmed") and w and c.get("banner_ar")):
            continue
        try:
            start = date.fromisoformat(w[0])
        except (ValueError, TypeError):
            continue
        if week.thu - timedelta(days=2) <= start <= week.thu + timedelta(days=horizon_days):
            return {"key": c["key"], "banner_ar": c["banner_ar"], "date": w[0], "ar": c.get("ar", "")}
    return None


def assemble(week, issue_no, now, chosen, verified, site_url, dropped, alternates, claims=None,
             verse_block=None, saying=None, occasion=None):
    p = schema.empty_payload(week.iso, week.label_ar, issue_no, base.now_iso(now))
    if verse_block:
        p["verse"] = verse_block
    if saying:
        p["saying"] = saying
    if occasion:
        p["occasion"] = occasion
    for s in p["sections"]:
        items = chosen.get(s["key"]) or []
        s["items"] = items
        s["layout"] = schema.layout_for(s["key"], len(items))
        if (claims or {}).get(s["key"]):
            s["claim"] = claims[s["key"]]
        if s["key"] == "fixtures":
            s["comp"] = saff.COMP
    p["verified_urls"] = sorted(verified)
    if site_url:
        p["site_url"] = site_url
    p["dropped"] = [{"ttl": d.get("ttl", ""), "reason": d.get("reason", "")} for d in dropped if d.get("ttl") and d.get("reason")]
    p["alternates"] = {k: [{"ttl": a.get("ttl") or ("%s – %s" % (a.get("home", ""), a.get("away", ""))),
                            "sub": a.get("sub", ""), "url": a.get("url", ""), "score": a.get("score", 0),
                            "reasons": a.get("reasons", [])} for a in v] for k, v in alternates.items()}
    return p


# ---------------- the build ----------------

def build_issue(now, http, search=None, load_json=None, dry_run=True, out_root=None,
                model_call=None, model=None, public_base=None, issue_id=None):
    """Cold start → files on disk + db rows. -> report dict. Never posts."""
    week = dates.week_for(now)
    report = {"week_of": week.iso, "dropped": [], "errors": [], "files": {}, "status": "building", "dry_run": bool(dry_run)}
    if issue_id is None:
        issue_no = db.next_issue_no()
        try:
            issue_id = db.open_issue(week.iso, issue_no)
        except sqlite3.IntegrityError:
            raise BuildError("an issue for %s already exists — use rebuild()" % week.iso)
    else:
        issue_no = int((db.issue(issue_id) or {}).get("issue_no") or db.next_issue_no())
    report["issue_id"], report["issue_no"] = issue_id, issue_no

    by = _collect(week, now, http, search, load_json, report)
    verified = _verify_and_prune(by, http, report)

    ctx = {"recent_urls": db.recent_issue_urls(6), "rulings": db.rulings(),
           "recent_titles": set()}
    for row in db.items(db.latest_issue()["id"]) if db.latest_issue() and db.latest_issue()["id"] != issue_id else []:
        ctx["recent_titles"].add(_fold_title((row.get("item") or {}).get("ttl")))
    picked = rank.choose(by, ctx)

    chosen = {}
    for section, prims in picked["primary"].items():
        polished = _polish(prims, model_call, model)
        keep = []
        for i, c in enumerate(polished):
            if _clean_enough(c):
                keep.append(c)
                continue
            # a slop-ridden primary is swapped for its first clean alternate, else dropped
            swapped = None
            for alt in picked["alternates"].get("%s.%d" % (section, i), []):
                alt2 = _polish([alt], model_call, model)[0]
                if _clean_enough(alt2):
                    swapped = alt2
                    break
            if swapped:
                keep.append(swapped)
            else:
                report["dropped"].append({"ttl": c.get("ttl", ""), "reason": "الصيغة ما طلعت نظيفة"})
        if section == "cinema" and len(keep) != 3:
            keep = []
        chosen[section] = keep

    site_url = _site_url(public_base)
    if site_url:
        ok = links.verify([site_url], http)
        site_url = ok.get(site_url, "")
        if site_url:
            verified.add(site_url)

    # ratings for the three films — cited, never scraped (collect/ratings.py); the exact
    # IMDb id from elcinema goes in the query so the tool opens the right page.
    for c in chosen.get("cinema") or []:
        if search is not None:
            try:
                c["ratings"] = ratings.fetch(c.get("name") or c.get("ttl"), c.get("imdb_id"), search, model=model, max_uses=5)
            except Exception:
                c["ratings"] = {"imdb": None, "rt": None, "sources": []}
    claims = _claims(chosen, model_call, model)
    dataset = report.get("dataset") or {}
    verse_block = None
    try:
        verse_block = verse.fetch(verse.pick_key((dataset.get("verses") or {}).get("keys"), issue_no), http, now)
    except Exception as e:
        report["errors"].append("verse: %s" % e)
    saying = pick_saying(issue_no)
    occasion = pick_occasion(dataset, week)

    owned = art.load_owned()
    for c in chosen.get("worth") or []:
        if not (c.get("art_hint") or {}).get("og"):
            og = art.og_hint(c.get("url", ""), http)
            if og:
                c["art_hint"] = {"og": og}
    items = {}
    for section, cands in chosen.items():
        items[section] = []
        for slot, c in enumerate(cands):
            if section == "fixtures":
                info = art.logos_for(c, http) or {"kind": "generated", "sha256": "", "src": ""}
            else:
                info = art.resolve(c, section, issue_no, slot, http, owned=owned)
            items[section].append(_item_from(c, info))

    if verse_block:
        verified.add(verse_block["source"]["url"])
    payload = assemble(week, issue_no, now, items, verified, site_url, report["dropped"], picked["alternates"], claims,
                       verse_block=verse_block, saying=saying, occasion=occasion)
    for k, alts in picked["alternates"].items():
        section, slot = k.split(".")
        db.add_candidates(issue_id, section, int(slot), alts)

    errs = schema.validate(payload)
    if errs:
        db.set_issue(issue_id, status="failed", error="; ".join(errs)[:2000], payload=payload)
        report["status"], report["errors"] = "failed", report["errors"] + errs
        return report

    out_dir = os.path.join(_out_root(out_root), str(issue_no))
    try:
        files = render_build.render(payload, {}, out_dir, issue_no, run_audit=True, guard_ctx=(week, now))
    except Exception as e:
        db.set_issue(issue_id, status="failed", error=("%s: %s" % (type(e).__name__, e))[:2000], payload=payload)
        report["status"] = "failed"
        report["errors"].append("render: %s: %s" % (type(e).__name__, e))
        return report

    db.set_issue(issue_id, status="preview", payload=payload, html_sha=files["html_sha"], error="")
    rows = []
    for s in payload["sections"]:
        for i, it in enumerate(s["items"]):
            rows.append(dict(it, section=s["key"], slot=i, state="primary"))
    for d in payload["dropped"]:
        rows.append({"section": "dropped", "slot": 0, "ttl": d["ttl"], "reason": d["reason"], "state": "dropped"})
    db.set_items(issue_id, rows)
    report.update({"status": "preview", "payload": payload, "files": files, "out_dir": out_dir})
    return report


# ---------------- owner actions (re-render from stored state) ----------------

def _rerender(issue_id, payload, now, out_root=None):
    week = dates.week_for(now)
    row = db.issue(issue_id)
    issue_no = int(row["issue_no"])
    out_dir = os.path.join(_out_root(out_root), str(issue_no))
    errs = schema.validate(payload)
    if errs:
        raise BuildError("; ".join(errs))
    files = render_build.render(payload, {}, out_dir, issue_no, run_audit=True, guard_ctx=(week, now))
    db.set_issue(issue_id, payload=payload, html_sha=files["html_sha"], status="preview", error="")
    return files


def apply_alternate(issue_id, section, slot, rank_no, http, now, who="owner", out_root=None):
    row = db.issue(issue_id)
    payload = row["payload"]
    cands = db.candidates(issue_id, section, slot)
    pick = next((c for c in cands if int(c["rank"]) == int(rank_no)), None)
    if not pick:
        raise BuildError("no alternate #%s for %s.%s" % (rank_no, section, slot))
    alt = pick["cand"]
    ok = links.verify([alt.get("url", "")], http)
    if not ok:
        raise BuildError("البديل رابطه ما يفتح")
    alt["url"] = ok[alt["url"]]
    payload["verified_urls"] = sorted(set(payload.get("verified_urls") or []) | {alt["url"]})
    sec = schema.section(payload, section)
    old = sec["items"][slot]
    if section == "fixtures":
        info = art.logos_for(alt, http) or {"kind": "generated", "sha256": "", "src": ""}
    else:
        info = art.resolve(alt, section, row["issue_no"], slot, http)
    alt = _polish([alt], None, None)[0]
    sec["items"][slot] = _item_from(alt, info)
    sec["layout"] = schema.layout_for(section, len(sec["items"]))
    files = _rerender(issue_id, payload, now, out_root)
    db.mark_candidate_used(pick["id"])
    db.add_ruling(issue_id, who, "alt", section=section, slot=slot,
                  detail={"from": old.get("ttl") or old.get("home"), "to": alt.get("ttl") or alt.get("home"),
                          "district": (old.get("tags") or {}).get("district"), "category": (old.get("tags") or {}).get("category"),
                          "source": (old.get("source") or {}).get("name")})
    return files


def drop_slot(issue_id, section, slot, now, who="owner", reason="حذفه فيصل", out_root=None):
    row = db.issue(issue_id)
    payload = row["payload"]
    sec = schema.section(payload, section)
    if not sec or slot >= len(sec["items"]):
        raise BuildError("no such slot")
    old = sec["items"].pop(slot)
    if section == "cinema":
        sec["items"] = []                      # cinema is three or nothing
    sec["layout"] = schema.layout_for(section, len(sec["items"]))
    payload.setdefault("dropped", []).append({"ttl": old.get("ttl") or ("%s – %s" % (old.get("home", ""), old.get("away", ""))), "reason": reason})
    files = _rerender(issue_id, payload, now, out_root)
    db.add_ruling(issue_id, who, "drop", section=section, slot=slot,
                  detail={"ttl": old.get("ttl"), "district": (old.get("tags") or {}).get("district"),
                          "category": (old.get("tags") or {}).get("category"), "source": (old.get("source") or {}).get("name")})
    return files


def rephrase(issue_id, now, model_call, model=None, who="owner", out_root=None):
    row = db.issue(issue_id)
    payload = row["payload"]
    seed = len([r for r in db.rulings_for(issue_id) if r["action"] == "rephrase"]) + 1
    # Owner rule (2026-09-03): facts lines never change; «غيّر الصيغة» rewrites the page
    # claims only, with a new seed so the model tries a different angle.
    for s in payload["sections"]:
        if not s.get("items"):
            continue
        c = voice.polish_claim(s["key"], s["items"], model_call=model_call, model=model, seed=seed)
        if c:
            s["claim"] = c
    files = _rerender(issue_id, payload, now, out_root)
    db.add_ruling(issue_id, who, "rephrase", detail={"seed": seed})
    return files


def rebuild(issue_id, now, http, search=None, load_json=None, who="owner", out_root=None, model_call=None, model=None, public_base=None):
    n = db.bump_rebuilds(issue_id)
    if n > MAX_REBUILDS:
        raise BuildError("وصلنا الحد: %d إعادات لهالعدد" % MAX_REBUILDS)
    db.add_ruling(issue_id, who, "rebuild", detail={"n": n})
    return build_issue(now, http, search=search, load_json=load_json, out_root=out_root,
                       model_call=model_call, model=model, public_base=public_base, issue_id=issue_id)


def approve(issue_id, now, who="owner"):
    """Marks the issue approved and records what he liked (rank.py learns from it)."""
    row = db.issue(issue_id)
    payload = row["payload"]
    districts, categories = set(), set()
    for s in payload.get("sections") or []:
        for it in s.get("items") or []:
            t = it.get("tags") or {}
            if t.get("district"):
                districts.add(t["district"])
            if t.get("category"):
                categories.add(t["category"])
    db.add_ruling(issue_id, who, "approve", detail={"districts": sorted(districts), "categories": sorted(categories)})
    db.set_issue(issue_id, status="approved")
    return row["issue_no"]


# ---------------- CLI ----------------

def _fixture_http():
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests", "fixtures", "digest"))
    from _fake_http import FakeHttp, fixture, HERE
    with open(os.path.join(HERE, "saff-roshn-20260902.html"), "rb") as fh:
        saff_html = fh.read().decode("cp1256", "replace")
    return FakeHttp(pages={
        platinumlist.CALENDAR_URL: (200, "text/html", fixture("platinumlist-this-weekend-20260902.html")),
        "https://riyadh.platinumlist.net/ar/event-tickets/107433/spacetoon-memories-with-assem-sukkar-in-riyadh":
            (200, "text/html", fixture("platinumlist-event-107433-20260902.html")),
        elcinema.NOW_URL: (200, "text/html", fixture("elcinema-now-sa-20260902.html")),
        saff.SCHEDULE_URL: (200, "text/html", saff_html),
        kooora.PAGE_URL: (200, "text/html", fixture("kooora-roshn-20260902.html")),
        podcast.FEED_URL: (200, "application/json", fixture("apple-podcasts-sa-top10-20260903.json")),
        verse.API % "94:5": (200, "application/json", fixture("quran-94-5-20260903.json")),
        verse.API % "94:6": (200, "application/json", fixture("quran-94-6-20260903.json")),
    }, permissive_head=True)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="digest.build")
    ap.add_argument("--dry-run", action="store_true", help="build files, never post (the only mode this CLI has)")
    ap.add_argument("--week", help="a date inside the target week, YYYY-MM-DD (default: today, Riyadh)")
    ap.add_argument("--fixtures", action="store_true", help="offline: read the saved pages in tests/fixtures/digest/")
    ap.add_argument("--out", help="output root (default $STATE_DIR/digest or ./.digest_out)")
    ap.add_argument("--db", help="sqlite path for brain.db (default: a temp file for --fixtures)")
    a = ap.parse_args(argv)
    if a.week:
        now = datetime.fromisoformat(a.week + "T13:00:00").replace(tzinfo=dates.RIYADH)
    else:
        now = datetime.now(dates.RIYADH)
    from brain import db as bdb
    if a.db:
        bdb.set_db_path_for_tests(a.db)
    elif a.fixtures:
        import tempfile
        bdb.set_db_path_for_tests(os.path.join(tempfile.mkdtemp(prefix="digestcli_"), "brain.db"))
    db.reset_init_cache()
    if a.fixtures:
        http = _fixture_http()
    else:
        from . import net_live as http
    if already_built(now):
        print("an issue for %s already exists in this db" % dates.week_for(now).iso)
        return 2
    rep = build_issue(now, http, search=None, dry_run=True, out_root=a.out or (os.path.join(os.getcwd(), ".digest_out")))
    print("issue", rep["issue_no"], "week", rep["week_of"], "status", rep["status"])
    for k, v in (rep.get("files") or {}).items():
        if k in ("pdf", "png", "json"):
            print("  ", k, v)
    p = rep.get("payload") or {}
    for s in p.get("sections") or []:
        print("  %s: %d items" % (s["key"], len(s["items"])))
        for it in s["items"]:
            print("     -", it.get("ttl") or ("%s × %s" % (it.get("home"), it.get("away"))), "|", it.get("sub") or it.get("when"), "|", (it.get("art") or {}).get("kind", ""))
    print("  dropped:", len(rep["dropped"]))
    for d in rep["dropped"]:
        print("     -", d.get("ttl"), "—", d.get("reason"))
    for e in rep["errors"]:
        print("  error:", e)
    return 0 if rep["status"] == "preview" else 1


if __name__ == "__main__":
    sys.exit(main())
