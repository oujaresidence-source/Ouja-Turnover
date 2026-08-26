/* /cp v2 production script — the approved mock's behavior, minus the review-only
   font switcher, plus what a static mock cannot do: a real POST to /api/cp/lead,
   a focus-trapped drawer dialog, and progressive enhancement over the real
   /cp/ar/more/<key> routes (no JS -> the links navigate; JS -> the drawer opens). */
(function(){
  var reduce=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var inst=document.getElementById('inst'),big=document.getElementById('instBig'),lbl=document.getElementById('instLabel'),who=document.getElementById('instWho'),src=document.getElementById('instSrc');
  var OCC=(inst&&inst.getAttribute('data-occ'))||'76.9';
  var MKT=(inst&&inst.getAttribute('data-mkt'))||'38';
  function flip(){ if(!inst)return; inst.classList.add('is-us'); lbl.textContent='الإشغال · عوجا، كامل المحفظة'; who.textContent='عوجا'; src.textContent='مقابل متوسط المدينة '+MKT+'% · '+(inst.getAttribute('data-asof')||''); }
  function run(){ if(!big)return; if(reduce){ big.textContent=OCC+'%'; flip(); return; } var s=null; function st(t){ if(!s)s=t; var p=Math.min((t-s)/700,1),e=1-Math.pow(1-p,3); big.textContent=(parseFloat(MKT)+(parseFloat(OCC)-parseFloat(MKT))*e).toFixed(1)+'%'; if(p<1) requestAnimationFrame(st); else big.textContent=OCC+'%'; } requestAnimationFrame(st); setTimeout(flip,120); }
  setTimeout(run,900);
  if(!reduce) setTimeout(function(){ document.querySelectorAll('[data-count]').forEach(function(el){ var to=+el.getAttribute('data-count'),s=null; function st(t){ if(!s)s=t; var p=Math.min((t-s)/900,1),e=1-Math.pow(1-p,3); el.textContent=Math.round(to*e).toLocaleString('en-US'); if(p<1) requestAnimationFrame(st);} requestAnimationFrame(st); }); },1300);
  var io=new IntersectionObserver(function(es){ es.forEach(function(e){ if(e.isIntersecting){ e.target.classList.add('in'); io.unobserve(e.target);} }); },{threshold:.15});
  document.querySelectorAll('.reveal').forEach(function(el){ io.observe(el); });
  var secs=[].slice.call(document.querySelectorAll('main section[id]')),links=document.querySelectorAll('#nav a');
  function onScroll(){ var y=window.scrollY+120,cur=''; secs.forEach(function(s){ if(s.offsetTop<=y) cur=s.id; }); links.forEach(function(a){ a.classList.toggle('is-active',a.getAttribute('href')==='#'+cur); }); }
  window.addEventListener('scroll',onScroll,{passive:true}); onScroll();
  document.querySelectorAll('.door[data-aud]').forEach(function(d){ d.addEventListener('click',function(){ var r=document.querySelector('input[name=audience][value='+d.getAttribute('data-aud')+']'); if(r) r.checked=true; }); });

  /* drawer — a focus-trapped dialog over the real /more routes */
  var drawer=document.getElementById('drawer'),scrim=document.getElementById('scrim'),dTitle=document.getElementById('dTitle'),lastFocus=null;
  function focusables(){ return drawer.querySelectorAll('a[href],button,input,select,textarea,[tabindex]:not([tabindex="-1"])'); }
  function trap(e){ if(e.key!=='Tab') return; var f=focusables(); if(!f.length) return; var first=f[0],last=f[f.length-1];
    if(e.shiftKey && document.activeElement===first){ e.preventDefault(); last.focus(); }
    else if(!e.shiftKey && document.activeElement===last){ e.preventDefault(); first.focus(); } }
  function openD(key){ var sec=drawer.querySelector('.dsec[data-d="'+key+'"]'); if(!sec) return false; drawer.querySelectorAll('.dsec').forEach(function(s){s.classList.remove('on')}); sec.classList.add('on'); dTitle.textContent=sec.getAttribute('data-title'); lastFocus=document.activeElement; drawer.classList.add('on'); scrim.classList.add('on'); drawer.setAttribute('aria-hidden','false'); drawer.scrollTop=0; document.body.style.overflow='hidden'; document.getElementById('dClose').focus(); drawer.addEventListener('keydown',trap); return true; }
  function closeD(){ drawer.classList.remove('on'); scrim.classList.remove('on'); drawer.setAttribute('aria-hidden','true'); document.body.style.overflow=''; drawer.removeEventListener('keydown',trap); if(lastFocus) lastFocus.focus(); }
  document.querySelectorAll('[data-drawer]').forEach(function(b){ b.addEventListener('click',function(e){ if(openD(b.getAttribute('data-drawer'))) e.preventDefault(); }); });
  document.getElementById('dClose').addEventListener('click',closeD); scrim.addEventListener('click',closeD);
  document.addEventListener('keydown',function(e){ if(e.key==='Escape') closeD(); });
  drawer.querySelectorAll('[data-close]').forEach(function(a){ a.addEventListener('click',function(){ closeD(); }); });

  /* reservation — the real POST */
  var form=document.getElementById('lead'),err=document.getElementById('err');
  function norm(s){ return s.replace(/[٠-٩]/g,function(d){return '٠١٢٣٤٥٦٧٨٩'.indexOf(d)}).replace(/[۰-۹]/g,function(d){return '۰۱۲۳۴۵۶۷۸۹'.indexOf(d)}).replace(/[^0-9]/g,''); }
  function fail(msg,el){ err.textContent=msg; err.style.display='block'; if(el) el.focus(); }
  if(form) form.addEventListener('submit',function(e){ e.preventDefault(); err.style.display='none';
    if(!form.name.value.trim()){ fail('اكتب اسمك حتى نعرف من نكلّم.',form.name); return; }
    if(norm(form.phone.value).length<9){ fail('رقم الجوال غير مكتمل — نحتاجه لتأكيد الموعد. أو استخدم الواتساب.',form.phone); return; }
    var btn=form.querySelector('button[type=submit]'); btn.disabled=true;
    var payload={ name:form.name.value.trim(), phone:form.phone.value, audience:form.audience.value, mode:form.mode.value, slot:form.slot.value, company_url:form.company_url.value };
    fetch(form.getAttribute('action'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})
      .then(function(r){ if(r.status===429) throw new Error('rate'); if(!r.ok) throw new Error('bad'); return r.json(); })
      .then(function(){ var mode=form.mode.value==='office'?'في مكتبنا بالرياض':'عن بُعد عبر اتصال مرئي';
        var ok=document.getElementById('okText'); if(ok&&ok.getAttribute('data-tpl')) ok.textContent='لقاؤك '+mode+'. '+ok.getAttribute('data-tpl');
        document.getElementById('resv').classList.add('sent'); })
      .catch(function(ex){ btn.disabled=false;
        fail(ex.message==='rate' ? 'وصلتنا طلبات كثيرة من جهازك — جرّب بعد قليل، أو تواصل عبر الواتساب.'
                                 : 'تعذّر الإرسال الآن — جرّب مرة أخرى، أو تواصل عبر الواتساب.'); });
  });
})();
