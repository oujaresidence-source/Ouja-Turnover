# -*- coding: utf-8 -*-
"""Frontend<->backend contract for the expense Approval Center.

Guards the EXACT drift classes that have reached the owner:
  - the chip badge must read the .count of the {count,sar} tab value
    (stringifying the object renders the literal '[object Object]');
  - the served tab shape must stay {count:int, sar:number};
  - every /erp/api/exp* path the JS calls must be a registered route;
  - every literal data-act token must have a handler;
  - T.ar and T.en must stay at parity and cover every literal t() key.
"""
import json
import pathlib
import re
import shutil
import subprocess
import unittest

import bot

JS = pathlib.Path("finance/static/erp.js").read_text("utf-8")
INIT = pathlib.Path("finance/__init__.py").read_text("utf-8")


class ChipContract(unittest.TestCase):
    def test_backend_tabs_shape_is_count_sar(self):
        bot._expenses.clear()
        bot._expenses["c1"] = {"id": "c1", "amount": 10.0, "expense_date": "2026-05-01",
                               "apartment": "Ouja | X", "listing_id": 1, "category": "صيانة",
                               "approval_status": "pending_approval"}
        tabs = bot._exp4_overview_data(tab="pending")["tabs"]
        self.assertEqual(set(tabs), {"pending", "approved", "exported", "verified", "needs_action"})
        for k, v in tabs.items():
            self.assertIsInstance(v, dict, k)
            self.assertIsInstance(v["count"], int, k)
            self.assertIsInstance(v["sar"], (int, float), k)

    def test_chip_renderer_reads_count_not_object(self):
        # the exact broken coercion must be gone, and the chip must read a .count off the tab value
        self.assertNotIn("' <b>' + tabs[k]", JS)
        chip_area = JS[JS.index("function renderExp"):JS.index("function loadExp")]
        self.assertIn("tabs[k]", chip_area)
        self.assertIn(".count", chip_area)


class RouteContract(unittest.TestCase):
    def test_every_exp_api_called_is_registered(self):
        routes = set(re.findall(r'add_(?:get|post|put|delete)\(\s*"([^"]+)"', INIT))
        called = set(re.findall(r"""api\(\s*['"](/erp/api/exp[^'"?]*)""", JS))
        called |= set(re.findall(r"""['"](/erp/api/exp[a-zA-Z0-9/_-]*)\??['"]""", JS))
        for c in called:
            c = c.rstrip("/")
            self.assertTrue(c in routes or any(c == r.rstrip("/") for r in routes),
                            "JS calls an unregistered route: " + c)


class DataActContract(unittest.TestCase):
    def test_every_literal_data_act_token_is_handled(self):
        acts = set(re.findall(r'data-act="([^"]+)"', JS))
        # drop dynamically-built tokens (data-act="' + x + '...") — those are not literals
        acts = {a for a in acts if "'" not in a and "+" not in a}
        branch = set(re.findall(r"act === '([^']+)'", JS))
        matched = set(re.findall(r"""\[data-act=\\?["']([^"'\]]+)""", JS))
        handled = branch | matched
        dead = sorted(a for a in acts if a not in handled)
        self.assertEqual(dead, [], "dead data-act tokens (no handler): " + repr(dead))


class BulkAffordance(unittest.TestCase):
    """expBulkAction is the single source of truth for terminal-state affordances.
    It is a pure function — eval it in isolation and assert the map so a future edit
    that re-offers Approve on verified/exported fails here, not on the owner's screen."""
    def test_bulk_action_map(self):
        if not shutil.which("node"):
            self.skipTest("node not available")
        probe = r"""
const fs=require('fs');const js=fs.readFileSync('finance/static/erp.js','utf8');
const s=js.indexOf('function expBulkAction');let d=0,b=js.indexOf('{',s),e=-1;
for(let p=b;p<js.length;p++){if(js[p]==='{')d++;else if(js[p]==='}'){d--;if(d===0){e=p+1;break;}}}
const fn=eval('('+js.slice(s,e)+')');
const out={};['pending','needs_action','approved','exported','verified'].forEach(t=>out[t]=fn(t));
console.log(JSON.stringify(out));
"""
        out = json.loads(subprocess.check_output(["node", "-e", probe], cwd=".").decode())
        self.assertEqual(out["pending"], "approve")
        self.assertEqual(out["needs_action"], "approve")
        self.assertEqual(out["approved"], "export")
        self.assertEqual(out["exported"], "")       # terminal — no bulk action (per-row recheck only)
        self.assertEqual(out["verified"], "")        # terminal — nothing


class I18nParity(unittest.TestCase):
    def test_ar_en_parity_and_coverage(self):
        if not shutil.which("node"):
            self.skipTest("node not available")
        probe = r"""
const fs=require('fs');const js=fs.readFileSync('finance/static/erp.js','utf8');
const i=js.indexOf('var T = {');let d=0,end=-1;
for(let p=js.indexOf('{',i);p<js.length;p++){if(js[p]==='{')d++;else if(js[p]==='}'){d--;if(d===0){end=p+1;break;}}}
const T=eval('('+js.slice(js.indexOf('{',i),end)+')');
const ar=Object.keys(T.ar),en=Object.keys(T.en),arS=new Set(ar),enS=new Set(en);
const used=new Set();const re=/\bt\(\s*['"]([A-Za-z0-9_]+)['"]\s*(\+)?/g;let m;
while((m=re.exec(js))){if(!m[2])used.add(m[1]);}
console.log(JSON.stringify({onlyAr:ar.filter(k=>!enS.has(k)),onlyEn:en.filter(k=>!arS.has(k)),
  absentAr:[...used].filter(k=>!arS.has(k)),absentEn:[...used].filter(k=>!enS.has(k))}));
"""
        r = json.loads(subprocess.check_output(["node", "-e", probe], cwd=".").decode())
        self.assertEqual(r["onlyAr"], [], "AR keys missing an EN twin")
        self.assertEqual(r["onlyEn"], [], "EN keys missing an AR twin")
        self.assertEqual(r["absentAr"], [], "t() keys absent from T.ar (would render the literal key)")
        self.assertEqual(r["absentEn"], [], "t() keys absent from T.en")


if __name__ == "__main__":
    unittest.main()
