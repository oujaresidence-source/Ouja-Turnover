# -*- coding: utf-8 -*-
"""
business.manage — the login-gated picker at /business/manage.

A small internal window: it lists the units from the Hostaway integration, lets the
owner tick 5-10 to feature on /business, order them, and write a short title, area,
and tagline per unit (the sectionized description, not the raw Hostaway blurb). The
real listing photo is pre-filled and editable. Saves to business_listings.json.

NORMAL triple-quoted string, ZERO backslashes, no inline-onclick quote-building —
same trap as the public page. esprima-parse the <script> after edits.
"""

MANAGE_HTML = """<!doctype html>
<html lang="en" dir="ltr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ouja · Featured residences</title>
<style>
:root{--bg:#FBF8F1;--panel:#fff;--ink:#221C14;--ink2:#5C5344;--muted:#837A69;
  --line:#E3D8C4;--gold:#A9781F;--ok:#4C7A52;--bad:#B0553C;--rad:12px}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:"IBM Plex Sans Arabic",system-ui,-apple-system,"Segoe UI",sans-serif;font-size:15px;line-height:1.5}
.wrap{max-width:900px;margin:0 auto;padding:28px 20px 80px}
h1{font-size:26px;margin:0 0 6px;letter-spacing:-0.01em}
.sub{color:var(--muted);margin:0 0 22px;font-size:14px}
.bar{position:sticky;top:0;background:rgba(251,248,241,.92);backdrop-filter:blur(8px);
  padding:14px 0;border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:center;z-index:5}
.btn{background:var(--gold);color:#fff;border:0;border-radius:10px;padding:11px 20px;font:inherit;
  font-weight:600;cursor:pointer}
.btn:disabled{opacity:.5;cursor:default}
.btn.ghost{background:transparent;color:var(--gold);border:1px solid var(--line)}
#status{font-size:13.5px;color:var(--muted)}
#status.ok{color:var(--ok)}
#status.err{color:var(--bad)}
.count-pill{font-size:13px;color:var(--muted);font-variant-numeric:tabular-nums}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--rad);
  padding:14px;margin:12px 0;display:grid;grid-template-columns:64px 1fr;gap:14px;align-items:start}
.card.on{border-color:var(--gold);box-shadow:0 0 0 1px var(--gold) inset}
.thumb{width:64px;height:64px;border-radius:8px;object-fit:cover;background:#EFE7D7}
.top{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.top label{font-weight:600;display:flex;align-items:center;gap:8px;cursor:pointer}
.name{color:var(--ink2);font-size:13.5px}
.fields{display:none;grid-template-columns:90px 1fr;gap:9px 12px;margin-top:12px}
.card.on .fields{display:grid}
.fields label{font-size:12px;color:var(--muted);align-self:center}
.fields input{font:inherit;font-size:14px;color:var(--ink);background:#fff;border:1px solid var(--line);
  border-radius:8px;padding:9px 11px;width:100%}
.fields input:focus{outline:none;border-color:var(--gold)}
.ord{width:64px!important}
.empty{color:var(--muted);padding:30px 0}
</style>
</head>
<body>
<div class="wrap">
  <h1>Featured residences</h1>
  <p class="sub">Tick the units to show on the public page (5 to 10 is ideal). Give each a short title, area, and one-line tagline. The photo is pulled from the listing; you can paste a different image URL.</p>
  <div class="bar">
    <button class="btn" id="save" type="button">Save</button>
    <button class="btn ghost" id="reload" type="button">Reload</button>
    <span class="count-pill" id="count">0 selected</span>
    <span id="status"></span>
  </div>
  <div id="list"><p class="empty">Loading units from Hostaway...</p></div>
</div>
<script>
(function(){
  var listEl = document.getElementById("list");
  var statusEl = document.getElementById("status");
  var countEl = document.getElementById("count");
  var saveBtn = document.getElementById("save");
  var options = [], saved = {};

  function esc(s){ return (s == null ? "" : String(s)); }
  function setStatus(msg, kind){ statusEl.textContent = msg || ""; statusEl.className = kind || ""; }
  function refreshCount(){
    var n = listEl.querySelectorAll(".card.on").length;
    countEl.textContent = n + " selected";
  }

  function rowFor(opt, sv){
    var id = opt.id;
    var on = !!sv;
    var card = document.createElement("div");
    card.className = "card" + (on ? " on" : "");
    card.setAttribute("data-id", id);

    var img = document.createElement("img");
    img.className = "thumb";
    img.src = (sv && sv.photo) || opt.photo || "";
    img.alt = "";
    card.appendChild(img);

    var right = document.createElement("div");
    var top = document.createElement("div");
    top.className = "top";
    var lab = document.createElement("label");
    var cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = on;
    cb.addEventListener("change", function(){
      card.classList.toggle("on", cb.checked);
      refreshCount();
    });
    lab.appendChild(cb);
    var nm = document.createElement("span");
    nm.className = "name";
    nm.textContent = esc(opt.name);
    lab.appendChild(nm);
    top.appendChild(lab);
    right.appendChild(top);

    var fields = document.createElement("div");
    fields.className = "fields";
    var defs = [
      ["order", "Order", (sv && sv.order != null) ? sv.order : ""],
      ["title", "Title", (sv && sv.title) || opt.name || ""],
      ["area", "Area", (sv && sv.area) || opt.city || ""],
      ["tagline", "Tagline", (sv && sv.tagline) || ""],
      ["photo", "Photo URL", (sv && sv.photo) || opt.photo || ""]
    ];
    for (var i = 0; i < defs.length; i++){
      var l = document.createElement("label"); l.textContent = defs[i][1];
      var inp = document.createElement("input");
      inp.setAttribute("data-f", defs[i][0]);
      inp.value = esc(defs[i][2]);
      if (defs[i][0] === "order"){ inp.className = "ord"; inp.type = "number"; }
      fields.appendChild(l); fields.appendChild(inp);
    }
    right.appendChild(fields);
    card.appendChild(right);
    return card;
  }

  function render(){
    listEl.innerHTML = "";
    if (!options.length){
      listEl.innerHTML = '<p class="empty">No units returned from Hostaway right now. Try Reload.</p>';
      return;
    }
    var savedById = {};
    (saved.listings || []).forEach(function(s, idx){
      if (s.order == null){ s.order = idx + 1; }
      savedById[s.id] = s;
    });
    // featured first (by order), then the rest
    var feat = [], rest = [];
    options.forEach(function(o){ (savedById[o.id] ? feat : rest).push(o); });
    feat.sort(function(a, b){ return (savedById[a.id].order || 0) - (savedById[b.id].order || 0); });
    feat.concat(rest).forEach(function(o){ listEl.appendChild(rowFor(o, savedById[o.id])); });
    refreshCount();
  }

  function load(){
    setStatus("Loading...", "");
    fetch("/api/business/manage").then(function(r){ return r.json(); }).then(function(d){
      if (!d.ok){ setStatus(d.error || "Failed to load", "err"); return; }
      options = d.options || [];
      saved = d.saved || {listings: []};
      render();
      setStatus("", "");
    }).catch(function(){ setStatus("Network error", "err"); });
  }

  function save(){
    var out = [];
    listEl.querySelectorAll(".card.on").forEach(function(card){
      var id = card.getAttribute("data-id");
      var rec = {id: id};
      card.querySelectorAll("input[data-f]").forEach(function(inp){
        var f = inp.getAttribute("data-f");
        var v = inp.value.trim();
        if (f === "order"){ rec.order = v === "" ? 999 : parseInt(v, 10); }
        else { rec[f] = v; }
      });
      out.push(rec);
    });
    out.sort(function(a, b){ return (a.order || 0) - (b.order || 0); });
    saveBtn.disabled = true;
    setStatus("Saving...", "");
    fetch("/api/business/listings", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({listings: out})
    }).then(function(r){ return r.json(); }).then(function(d){
      saveBtn.disabled = false;
      if (d.ok){ setStatus("Saved " + out.length + " residences. Live on /business.", "ok"); saved = {listings: out}; }
      else { setStatus(d.error || "Save failed", "err"); }
    }).catch(function(){ saveBtn.disabled = false; setStatus("Network error", "err"); });
  }

  saveBtn.addEventListener("click", save);
  document.getElementById("reload").addEventListener("click", load);
  load();
})();
</script>
</body>
</html>"""
