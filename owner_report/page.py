# -*- coding: utf-8 -*-
"""
owner_report.page — the standalone bilingual Owner Report wizard at /owner-report.

SAME BACKSLASH TRAP as DASHBOARD_HTML / schedule.page: this is a normal triple-quoted
string, so a backslash escape (\\n, \\t, \\s) would be consumed by Python and can break
the embedded JS. This file therefore contains ZERO backslashes — real newlines only, event
delegation (no inline-onclick quote-building), and no regex/JSON escapes in JS string
literals. esprima-parse every <script> block after any edit.

The wizard: pick unit -> period -> gated answers (each re-confirmed) -> advanced (full
operator template as JSON) -> reconcile + sign-off -> preview -> export. It renders from the
question bank the server sends; the reconciliation chain and validation come from the same
pure pipeline the PDF uses, so preview equals export to the riyal.
"""

OWNER_REPORT_PAGE_HTML = """<!DOCTYPE html><html lang="ar"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ouja — Owner Report Wizard</title>
<style>
:root{--paper:#FFFDF9;--cream:#F7F2E7;--cream2:#EFE8D9;--ink:#1B1915;--ink2:#4A443B;
 --muted:#8C8477;--gold:#B4924A;--goldl:#D9C48A;--rule:#E3DBC8;--pos:#2E6B4F;--warn:#B5722A;--neg:#A4433A}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,Segoe UI,Tajawal,sans-serif;background:var(--paper);color:var(--ink);
 font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased}
.wrap{max-width:1040px;margin:0 auto;padding:22px 18px 80px}
header{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:2px solid var(--gold);
 padding-bottom:12px;margin-bottom:18px;gap:14px;flex-wrap:wrap}
h1{font-size:20px;font-weight:600;letter-spacing:-.01em}
h1 .ar{display:block;font-size:15px;color:var(--ink2);font-weight:500}
.kick{font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--gold);font-weight:600}
.card{background:var(--cream);border:1px solid var(--rule);border-top:2px solid var(--gold);
 border-radius:4px;padding:16px;margin-bottom:16px}
.card h2{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink2);
 margin-bottom:12px;display:flex;justify-content:space-between;align-items:baseline}
.card h2 .ar{font-size:13px;color:var(--gold);text-transform:none;letter-spacing:0}
label{display:block;font-size:11px;color:var(--muted);margin-bottom:4px;font-weight:600}
input,select,textarea{width:100%;font:inherit;padding:7px 9px;border:1px solid var(--rule);
 border-radius:3px;background:var(--paper);color:var(--ink)}
textarea{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;min-height:90px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}
.q{border-bottom:1px dotted var(--rule);padding:10px 0}
.q .qt{font-size:13px;margin-bottom:2px}
.q .qa{font-size:12px;color:var(--ink2);direction:rtl;text-align:right}
.q .note{font-size:11px;color:var(--muted);margin-top:3px}
.q .row{display:flex;gap:10px;align-items:center;margin-top:6px}
.q .row .grow{flex:1}
.confirm{display:flex;align-items:center;gap:5px;font-size:11px;color:var(--muted);white-space:nowrap}
.confirm input{width:auto}
.confirm.on{color:var(--pos);font-weight:600}
button{font:inherit;font-weight:600;border:0;border-radius:4px;padding:9px 16px;cursor:pointer;
 background:var(--ink);color:var(--goldl)}
button.ghost{background:var(--paper);color:var(--ink);border:1px solid var(--rule)}
button:disabled{opacity:.45;cursor:not-allowed}
.bar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:6px}
.tot{width:100%;border-collapse:collapse;font-size:13px;margin-top:6px}
.tot td{padding:6px 8px;border-bottom:1px solid var(--rule)}
.tot td.n{text-align:right;font-variant-numeric:tabular-nums}
.tot tr.grand td{background:var(--ink);color:var(--goldl);font-weight:600;border:0}
.pill{display:inline-block;padding:2px 8px;border-radius:9px;font-size:11px;font-weight:600}
.pill.h{background:#F5E4E2;color:var(--neg)} .pill.s{background:#F7EBDC;color:var(--warn)}
.pill.ok{background:#E4EFE9;color:var(--pos)}
.msg{font-size:12px;padding:8px 10px;border-radius:4px;margin-top:8px}
.msg.err{background:#F5E4E2;color:var(--neg)} .msg.ok{background:#E4EFE9;color:var(--pos)}
.tags{display:flex;gap:8px;font-size:11px;color:var(--muted);margin-top:8px}
.hidden{display:none}
.hist{font-size:12px}
.hist div{padding:4px 0;border-bottom:1px dotted var(--rule);display:flex;justify-content:space-between}
@media(max-width:640px){.grid,.grid3{grid-template-columns:1fr}}
</style></head>
<body><div class="wrap">
<header>
 <div><div class="kick">Ouja Residence · Revenue &amp; Asset Management</div>
  <h1>Owner Performance Report<span class="ar">تقرير أداء المالك — معالج الإصدار</span></h1></div>
 <div style="text-align:right"><label>Unit / الوحدة</label>
  <select id="unit" style="min-width:240px"></select></div>
</header>

<div class="card"><h2>1 · Scope <span class="ar">النطاق</span></h2>
 <div class="grid3">
  <div><label>Period start / بداية الفترة</label><input type="date" id="pstart"></div>
  <div><label>Period end / نهاية الفترة</label><input type="date" id="pend"></div>
  <div><label>Months / عدد الأشهر</label>
   <select id="months"><option value="6">6 (half-year)</option><option value="12">12 (full year)</option></select></div>
 </div>
</div>

<div class="card"><h2 id="gh">2 · Gated answers <span class="ar">الأسئلة الإلزامية</span></h2>
 <div id="gated"></div>
</div>

<div class="card"><h2>3 · Advanced — full operator template
  <span class="ar">القالب الكامل (JSON)</span></h2>
 <label>Everything the report needs that is not auto-pulled from Hostaway (unit meta, Ejar
  details, comp set, factors, risks, actions, sources, projection, opex). Edited as JSON,
  stored per unit.</label>
 <textarea id="tpl" spellcheck="false"></textarea>
 <div class="bar"><button class="ghost" id="save">Save template / حفظ القالب</button>
  <span id="savemsg" class="hist"></span></div>
</div>

<div class="card"><h2>4 · Reconcile &amp; sign-off <span class="ar">المطابقة والاعتماد</span></h2>
 <div class="bar"><button id="recon">Reconcile / احسب المطابقة</button>
  <span id="tagsline" class="tags"></span></div>
 <div id="reconbox"></div>
</div>

<div class="card"><h2>5 · Preview &amp; export <span class="ar">المعاينة والإصدار</span></h2>
 <div class="bar">
  <button class="ghost" id="preview" disabled>Preview draft / معاينة</button>
  <button id="export" disabled>Export &amp; issue / إصدار</button>
  <span id="buildmsg" class="hist"></span>
 </div>
</div>

<div class="card"><h2>Issued reports <span class="ar">التقارير الصادرة</span></h2>
 <div id="history" class="hist"></div>
</div>

</div>
<script>
var S={bank:null,sections:[],confirm:{},lastRecon:null,signed:false};

var TOK=new URLSearchParams(location.search).get("token")||"";
function withTok(path){ if(!TOK) return path; return path+(path.indexOf("?")>=0?"&":"?")+"token="+encodeURIComponent(TOK); }
function el(id){return document.getElementById(id);}
function api(path,opts){return fetch(withTok(path),opts).then(function(r){return r.json();});}
function money(n){return (n==null)?"—":Number(n).toLocaleString("en-US");}

function loadUnits(){
 return api("/api/owner-report/units").then(function(d){
  var u=el("unit"); u.innerHTML="";
  (d.units||[]).forEach(function(x){
   var o=document.createElement("option"); o.value=x.lid; o.textContent=x.name+"  ("+x.lid+")"; u.appendChild(o);
  });
 });
}

function loadBank(){
 return api("/api/owner-report/questions").then(function(d){ S.bank=d.bank; S.sections=d.sections; });
}

// Gated scalar questions the validator keys on (a focused subset of the bank).
var GATED=["vat_basis","owner_blocked_nights","owner_blocked_treatment","mgmt_fee_pct",
 "purchase_price","ejar_annual_rent","ejar_is_single_contract","ejar_furnished",
 "furnished_uplift_pct","delivered_furnished","comp_observed","manual_bookings","channel_fees"];

function findQ(id){
 var found=null;
 Object.keys(S.bank||{}).forEach(function(s){
  (S.bank[s]||[]).forEach(function(q){ if(q.id===id) found=q; });
 });
 return found;
}

function renderGated(){
 var box=el("gated"); box.innerHTML="";
 GATED.forEach(function(id){
  var q=findQ(id);
  var qt=q?q.en:id, qa=q?q.ar:"", note=q?(q.note_en||""):"";
  var div=document.createElement("div"); div.className="q"; div.dataset.qid=id;
  var input="";
  if(q && q.kind==="choice" && q.options.length){
   var opts=q.options.map(function(o){return "<option value="+JSON.stringify(o.value)+">"+o.en+" · "+o.ar+"</option>";}).join("");
   input="<select class='grow' data-in='"+id+"'>"+opts+"</select>";
  } else {
   var t=(q && (q.kind==="money"||q.kind==="number"||q.kind==="percent"))?"number":"text";
   input="<input class='grow' type='"+t+"' step='any' data-in='"+id+"'>";
  }
  div.innerHTML="<div class='qt'>"+qt+"</div><div class='qa'>"+qa+"</div>"+
   (note?"<div class='note'>"+note+"</div>":"")+
   "<div class='row'>"+input+
   "<label class='confirm' data-cf='"+id+"'><input type='checkbox' data-ck='"+id+"'>confirm / أؤكد</label></div>";
  box.appendChild(div);
 });
}

// channel_fees is not in the bank (it is a cost input) — patch its labels.
function patchExtraLabels(){
 var d=document.querySelector("[data-qid=channel_fees] .qt"); if(d) d.textContent="Channel fees for the period (SAR)";
 var a=document.querySelector("[data-qid=channel_fees] .qa"); if(a) a.textContent="رسوم القنوات للفترة (ريال)";
}

function currentValues(){
 var v={}; document.querySelectorAll("[data-in]").forEach(function(x){ v[x.dataset.in]=x.value; });
 return v;
}
function confirmations(){
 var c={}; document.querySelectorAll("[data-ck]").forEach(function(x){ c[x.dataset.ck]=x.checked; });
 return c;
}
function allConfirmed(){
 var c=confirmations(); return Object.keys(c).length>0 && Object.keys(c).every(function(k){return c[k];});
}

function tpl(){ try{ return JSON.parse(el("tpl").value); }catch(e){ return null; } }

function loadWizard(lid){
 return api("/api/owner-report/wizard?lid="+encodeURIComponent(lid)).then(function(d){
  el("tpl").value=JSON.stringify(d.values||{},null,2);
  // seed gated inputs from stored template values where present
  var v=d.values||{};
  setIn("vat_basis", v.vat_basis);
  setIn("owner_blocked_treatment", v.owner_blocked_treatment);
  setIn("mgmt_fee_pct", v.costs?v.costs.mgmt_fee_pct:"");
  setIn("purchase_price", v.asset?v.asset.purchase_price:"");
  setIn("ejar_annual_rent", v.ejar?v.ejar.annual_rent:"");
  setIn("ejar_is_single_contract", v.ejar_is_single_contract?"single":"sample");
  setIn("ejar_furnished", (v.ejar&&v.ejar.comparable_furnished)?"furnished":"unfurnished");
  setIn("furnished_uplift_pct", v.ejar?v.ejar.furnished_uplift_pct:"");
  setIn("delivered_furnished", (v.furnishing&&v.furnishing.delivered_furnished)?"true":"false");
  setIn("channel_fees", v.costs?v.costs.channel_fees:"");
 });
}
function setIn(id,val){ var x=document.querySelector("[data-in="+id+"]"); if(x&&val!=null&&val!=="") x.value=val; }

// merge gated answers back into the JSON template so the server gets one coherent object
function mergedValues(){
 var v=tpl()||{}; var g=currentValues();
 v.vat_basis=g.vat_basis||v.vat_basis;
 v.owner_blocked_treatment=g.owner_blocked_treatment||v.owner_blocked_treatment;
 v.costs=v.costs||{}; if(g.mgmt_fee_pct!=="") v.costs.mgmt_fee_pct=Number(g.mgmt_fee_pct);
 if(g.channel_fees!=="") v.costs.channel_fees=Number(g.channel_fees);
 v.asset=v.asset||{}; if(g.purchase_price!=="") v.asset.purchase_price=Number(g.purchase_price);
 v.ejar=v.ejar||{}; if(g.ejar_annual_rent!=="") v.ejar.annual_rent=Number(g.ejar_annual_rent);
 v.ejar.comparable_furnished=(g.ejar_furnished==="furnished");
 if(g.furnished_uplift_pct!=="") v.ejar.furnished_uplift_pct=Number(g.furnished_uplift_pct);
 v.ejar_is_single_contract=(g.ejar_is_single_contract==="single");
 v.furnishing=v.furnishing||{}; v.furnishing.delivered_furnished=(g.delivered_furnished==="true");
 v.comp_stale=(g.comp_observed==="estimated")?v.comp_stale:v.comp_stale;
 if(g.manual_bookings!=="") v.manual_bookings=Number(g.manual_bookings);
 return v;
}

function buildPayload(extra){
 var b={lid:el("unit").value, values:mergedValues(),
  period_start:el("pstart").value, period_end:el("pend").value, months:Number(el("months").value),
  vat_resolved:confirmations().vat_basis===true,
  vat_reconciled_against_payout:confirmations().vat_basis===true,
  owner_blocked_nights:Number(currentValues().owner_blocked_nights||0),
  owner_blocked_treatment:currentValues().owner_blocked_treatment,
  ejar_is_single_contract:currentValues().ejar_is_single_contract==="single",
  ejar_unfurnished_no_uplift:(currentValues().ejar_furnished==="unfurnished" &&
    Number(currentValues().furnished_uplift_pct||0)===0),
  comp_stale:currentValues().comp_observed==="estimated",
  manual_bookings:Number(currentValues().manual_bookings||0),
  channel_fees:Number(currentValues().channel_fees||0),
  required_fields_confirmed:allConfirmed(),
  acknowledged:[], reconciliation_signed:S.signed};
 // acknowledge every soft warning the reconcile step surfaced
 if(S.lastRecon && S.lastRecon.soft) b.acknowledged=S.lastRecon.soft.map(function(w){return w.code;});
 if(extra) Object.keys(extra).forEach(function(k){ b[k]=extra[k]; });
 return b;
}

function doReconcile(){
 el("reconbox").innerHTML="<div class='hist'>…</div>";
 api("/api/owner-report/reconcile",{method:"POST",headers:{"Content-Type":"application/json"},
   body:JSON.stringify(buildPayload())}).then(function(d){
  if(!d.ok){ el("reconbox").innerHTML="<div class='msg err'>"+(d.error||"error")+"</div>"; return; }
  S.lastRecon=d;
  el("tagsline").innerHTML=["H","O","M","C"].map(function(t){return t+":"+(d.tags[t]||0);}).join(" · ")+
   " · Hostaway total "+money(d.hostaway_revenue_total);
  var r=d.reconciliation;
  var rows="<table class='tot'>"+
   "<tr><td>Gross revenue · إجمالي الإيراد</td><td class='n'>"+money(r.gross)+"</td></tr>"+
   "<tr><td>− Channel fees · رسوم القنوات</td><td class='n'>"+money(r.channel_fees)+"</td></tr>"+
   "<tr><td>Net rental · صافي الإيجار</td><td class='n'>"+money(r.net_rental)+"</td></tr>"+
   "<tr><td>− Management fee · رسوم الإدارة</td><td class='n'>"+money(r.mgmt_fee)+"</td></tr>"+
   "<tr><td>− Opex · التشغيل</td><td class='n'>"+money(r.opex_total)+"</td></tr>"+
   "<tr class='grand'><td>Net to owner · صافي المالك</td><td class='n'>"+money(r.owner_net)+"</td></tr>"+
   "</table>"+
   "<div class='hist'>Occupancy "+(r.occupancy!=null?(r.occupancy*100).toFixed(1)+"%":"—")+
   " · ADR "+money(r.adr)+" · RevPAR "+money(r.revpar)+"</div>";
  var issues="";
  (d.hard||[]).forEach(function(h){ issues+="<div class='msg err'><span class='pill h'>HARD</span> "+h+"</div>"; });
  (d.soft||[]).forEach(function(s){ issues+="<div class='msg' style='background:#F7EBDC'><span class='pill s'>DISCLOSE</span> "+s.msg+"</div>"; });
  var sign="";
  if(d.can_render){
   sign="<label class='confirm' style='margin-top:10px'><input type='checkbox' id='signck'>"+
    "I have reviewed the reconciliation against Hostaway and sign it off / راجعت المطابقة وأعتمدها</label>";
  } else {
   sign="<div class='msg err'>Resolve the HARD gates above before the reconciliation can be signed.</div>";
  }
  el("reconbox").innerHTML=rows+issues+sign;
  var sc=el("signck");
  if(sc) sc.addEventListener("change",function(){ S.signed=sc.checked; refreshButtons(); });
  refreshButtons();
 });
}

function refreshButtons(){
 var ready=S.lastRecon && S.lastRecon.can_render && allConfirmed();
 el("preview").disabled=!ready;
 el("export").disabled=!(ready && S.signed);
}

function doBuild(kind){
 el("buildmsg").textContent="Rendering… / جارِ الإصدار…";
 api("/api/owner-report/"+kind,{method:"POST",headers:{"Content-Type":"application/json"},
   body:JSON.stringify(buildPayload())}).then(function(d){
  if(!d.ok){
   var extra=d.violations?(" — "+d.violations.join("; ")):"";
   el("buildmsg").innerHTML="<span class='pill h'>BLOCKED</span> "+(d.error||"error")+extra; return;
  }
  el("buildmsg").innerHTML="<span class='pill ok'>"+(d.draft?"DRAFT":"ISSUED "+d.doc_ref)+"</span> "+
   "<a href='"+withTok(d.pdf)+"' target='_blank'>open PDF</a>";
  if(kind==="export") loadHistory();
 });
}

function loadHistory(){
 api("/api/owner-report/history").then(function(d){
  el("history").innerHTML=(d.history||[]).map(function(h){
   return "<div><span>"+h.doc_ref+"</span><span>"+h.status+
    (h.superseded_by?(" → "+h.superseded_by):"")+" · "+(h.created_at||"").slice(0,10)+"</span></div>";
  }).join("")||"<div>No reports issued yet.</div>";
 });
}

// wiring (event delegation / explicit listeners; no inline handlers)
document.addEventListener("change",function(e){
 if(e.target.matches("[data-ck]")){
  var lab=e.target.closest(".confirm"); if(lab) lab.classList.toggle("on",e.target.checked);
  refreshButtons();
 }
 if(e.target.id==="unit"){ onUnit(); }
});
document.addEventListener("input",function(e){ if(e.target.matches("[data-in]")){ S.signed=false; var s=el("signck"); if(s) s.checked=false; refreshButtons(); } });

function onUnit(){ var lid=el("unit").value; if(lid){ loadWizard(lid); S.signed=false; S.lastRecon=null; el("reconbox").innerHTML=""; refreshButtons(); } }

el("save").addEventListener("click",function(){
 var v=tpl(); if(!v){ el("savemsg").textContent="Invalid JSON"; return; }
 api("/api/owner-report/wizard",{method:"POST",headers:{"Content-Type":"application/json"},
   body:JSON.stringify({lid:el("unit").value,values:v})}).then(function(d){
  el("savemsg").textContent=d.ok?"Saved.":(d.error||"error");
 });
});
el("recon").addEventListener("click",doReconcile);
el("preview").addEventListener("click",function(){doBuild("preview");});
el("export").addEventListener("click",function(){doBuild("export");});

loadUnits().then(loadBank).then(function(){
 renderGated(); patchExtraLabels(); loadHistory();
 if(el("unit").value) onUnit();
});
</script>
</body></html>"""
