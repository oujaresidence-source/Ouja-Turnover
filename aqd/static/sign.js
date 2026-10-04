/* «العقود» — the client's signing page (/sign/{token}).
 *
 * Served by aqd/routes.py at /aqd/static/sign.js. A real file on purpose: the page shell in
 * aqd/sign_page.py is a Python string that eats backslashes; this file is not.
 *
 * Flow: GET /api/aqd-t/{token} (no contract body) → POST open → last-4 identity check
 * (POST verify returns a 30-minute view key + the contract) → read → typed name + drawn
 * signature + consent → POST sign → download. Must pass `node --check`.
 */
(function () {
  'use strict';

  var TOKEN = decodeURIComponent((location.pathname.split('/sign/')[1] || '').split('/')[0] || '');
  var S = { info: null, key: '', html: '', approved: false, state: '', readOk: false, busy: false,
            pad: null, signer: '' };

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return (s == null ? '' : String(s)).replace(/[<>&"']/g, function (c) {
      return { '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function put(h) { $('view').innerHTML = h; }
  function cta(show, label, enabled) {
    var c = $('cta'), b = $('signBtn');
    c.hidden = !show;
    if (label) b.textContent = label;
    b.disabled = !enabled;
  }

  async function getJSON(url) {
    var r = await fetch(url, { headers: { 'Accept': 'application/json' }, cache: 'no-store' });
    return r.json().catch(function () { return { ok: false, error: 'صار خطأ مؤقت — حدّث الصفحة' }; });
  }
  async function postJSON(url, body) {
    var r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
    return r.json().catch(function () { return { ok: false, error: 'صار خطأ مؤقت — حدّث الصفحة' }; });
  }

  function num(x) { var n = Number(x); return isFinite(n) ? (Math.round(n * 10) / 10) : '—'; }

  /* ---------------- one-sentence states ---------------- */
  function stateCard(kind, title, sub, extra) {
    var path = kind === 'ok' ? '<path d="M5 12.5l4.5 4.5L19 7.5"/>'
      : (kind === 'bad' ? '<path d="M12 7v6"/><path d="M12 17h.01"/>' : '<circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/>');
    var ic = '<svg viewBox="0 0 24 24" focusable="false">' + path + '</svg>';
    return '<section class="card state"><div class="ic ' + kind + '" aria-hidden="true">' + ic + '</div>'
      + '<h2>' + esc(title) + '</h2>' + (sub ? '<p>' + esc(sub) + '</p>' : '') + (extra || '') + '</section>';
  }

  function showState(st, err) {
    cta(false);
    if (st === 'void') return put(stateCard('bad', 'هذا العقد أُلغي', 'إذا تحتاج عقد جديد تواصل مع مدير حسابك في عوجا.'));
    if (st === 'expired') return put(stateCard('bad', 'انتهت صلاحية الرابط — تواصل مع مدير حسابك', 'نقدر نرسل لك رابط جديد لنفس العقد.'));
    if (st === 'busy') return put(stateCard('wait', 'طلبات كثيرة', 'انتظر دقيقة وحدّث الصفحة.'));
    if (st === 'locked') return put(stateCard('bad', 'حاولت كثير — جرّب بعد ساعة', 'للحماية وقفنا التحقق مؤقتاً.'));
    return put(stateCard('bad', 'الرابط غير صحيح', err && err !== 'الرابط غير صحيح' ? err : 'تأكد إنك فتحت الرابط كامل كما وصلك، أو تواصل مع مدير حسابك.'));
  }

  /* ---------------- boot ---------------- */
  async function boot() {
    if (!TOKEN || TOKEN.length < 20) return showState('invalid');
    var r = await getJSON('/api/aqd-t/' + encodeURIComponent(TOKEN));
    if (!r || !r.ok) return showState(r && r.state, r && r.error);
    S.info = r;
    $('ref').textContent = r.ref || '';
    if (r.state === 'void' || r.state === 'expired') return showState(r.state);
    postJSON('/api/aqd-t/open', { token: TOKEN });
    if (r.locked) return showState('locked');
    renderGate();
  }

  function greetingCard() {
    var r = S.info;
    var who = r.client_kind === 'company' ? r.greeting : ((r.honorific ? r.honorific + ' ' : '') + r.greeting);
    return '<section class="card">'
      + '<div class="hello">أهلاً ' + esc(who) + '</div>'
      + '<p class="lede">هذا عقد تشغيل وحداتك مع عوجا. تحقق، اقرأ، ووقّع من نفس الصفحة.</p>'
      + '<ul class="facts">'
      + '<li><span class="v">' + esc(r.units_count) + '</span><span class="l">' + (Number(r.units_count) === 1 ? 'وحدة' : 'وحدات') + '</span></li>'
      + '<li><span class="v">' + esc(num(r.op_pct)) + '%</span><span class="l">نسبة التشغيل</span></li>'
      + '<li><span class="v">12</span><span class="l">شهر مدة العقد</span></li>'
      + '</ul></section>';
  }

  /* ---------------- identity gate ---------------- */
  function renderGate() {
    var r = S.info;
    var src = r.client_kind === 'company' ? 'من السجل التجاري' : 'من هويتك';
    var digits = r.last4_kind !== 'alnum';
    var boxes = '';
    for (var i = 0; i < 4; i++) {
      boxes += '<input id="d' + i + '" maxlength="1" autocomplete="one-time-code" '
        + (digits ? 'inputmode="numeric" pattern="[0-9]*" ' : 'inputmode="text" autocapitalize="characters" ')
        + 'aria-label="الخانة ' + (i + 1) + ' من 4">';
    }
    put(greetingCard()
      + '<section class="card gate" aria-labelledby="gateT">'
      + '<h2 id="gateT">للحماية، اكتب آخر 4 أرقام ' + esc(src) + '</h2>'
      + '<p class="small">نتأكد إن العقد يوصل لصاحبه قبل ما يظهر.</p>'
      + '<div class="boxes" id="boxes" dir="ltr">' + boxes + '</div>'
      + '<p class="msg" id="gateMsg" role="alert"></p>'
      + '</section>');
    cta(true, 'تحقّق وافتح العقد', false);
    var ins = [0, 1, 2, 3].map(function (i) { return $('d' + i); });
    ins.forEach(function (el, i) {
      el.addEventListener('input', function () {
        var v = (el.value || '').replace(/[٠-٩]/g, function (c) { return String(c.charCodeAt(0) - 1632); });
        v = digits ? v.replace(/[^0-9]/g, '') : v.replace(/[^0-9A-Za-z]/g, '').toUpperCase();
        if (v.length > 1) {                      /* pasted all four */
          v.split('').slice(0, 4 - i).forEach(function (ch, k) { ins[i + k].value = ch; });
          ins[Math.min(3, i + v.length - 1)].focus();
        } else {
          el.value = v;
          if (v && i < 3) ins[i + 1].focus();
        }
        $('boxes').classList.remove('bad');
        $('gateMsg').textContent = '';
        var code = ins.map(function (x) { return x.value; }).join('');
        $('signBtn').disabled = code.length !== 4;
        if (code.length === 4) verify(code);
      });
      el.addEventListener('keydown', function (ev) {
        if (ev.key === 'Backspace' && !el.value && i > 0) { ins[i - 1].focus(); ins[i - 1].value = ''; }
        if (ev.key === 'Enter') { var c = ins.map(function (x) { return x.value; }).join(''); if (c.length === 4) verify(c); }
      });
    });
    $('signBtn').onclick = function () {
      var c = ins.map(function (x) { return x.value; }).join('');
      if (c.length === 4) verify(c);
    };
    setTimeout(function () { try { ins[0].focus(); } catch (_) {} }, 50);
  }

  async function verify(code) {
    if (S.busy) return;
    S.busy = true;
    $('signBtn').disabled = true;
    $('signBtn').textContent = 'جاري التحقق…';
    var r = await postJSON('/api/aqd-t/verify', { token: TOKEN, last4: code });
    S.busy = false;
    if (!r || !r.ok) {
      if (r && r.locked) return showState('locked');
      if (r && /أُلغي/.test(r.error || '')) return showState('void');
      if (r && /انتهت صلاحية/.test(r.error || '')) return showState('expired');
      var b = $('boxes');
      if (b) {
        b.classList.add('bad');
        b.classList.remove('shake'); void b.offsetWidth; b.classList.add('shake');
        [0, 1, 2, 3].forEach(function (i) { $('d' + i).value = ''; });
        $('d0').focus();
      }
      $('gateMsg').className = 'msg bad';
      $('gateMsg').textContent = (r && r.error) || 'البيانات غير صحيحة';
      $('signBtn').textContent = 'تحقّق وافتح العقد';
      return;
    }
    S.key = r.view_key; S.html = r.html; S.approved = !!r.approved; S.state = r.state; S.signer = r.signer_name || '';
    renderContract();
  }

  /* ---------------- the contract ---------------- */
  function fileUrl() { return '/api/aqd-t/' + encodeURIComponent(TOKEN) + '/file?k=' + encodeURIComponent(S.key); }

  var SCREEN_CSS = '<style>@media screen{html{background:#fff}body{padding:18px 16px 24px;font-size:15px}'
    + 'table.grid{display:block;overflow-x:auto;max-width:100%}.sigbox{grid-template-columns:1fr}'
    + '.ver{margin:0 0 10px}}</style>';

  function docHtml() {
    var h = S.html || '';
    var i = h.indexOf('</head>');
    return i >= 0 ? h.slice(0, i) + SCREEN_CSS + h.slice(i) : SCREEN_CSS + h;
  }

  function renderContract() {
    var st = S.state;
    var head = '';
    if (st === 'completed') {
      head = '<div class="note ok">العقد مكتمل — حمّل نسختك النهائية.</div>';
    } else if (st === 'signed_owner') {
      head = '<div class="note ok">وقّعت العقد. بنرسل لك النسخة النهائية بعد توقيع عوجا على نفس الرابط.</div>';
    } else if (!S.approved) {
      head = '<div class="note warn">التوقيع غير متاح — النموذج قيد المراجعة القانونية. تقدر تقرأ العقد وتحمّل نسخة للاطلاع.</div>';
    }
    var h = head
      + '<div class="bar" role="region" aria-label="تقدّم القراءة"><span class="lbl">اقرأ العقد كامل</span>'
      + '<span class="prog" aria-hidden="true"><i id="prog"></i></span>'
      + '<a class="link" id="dl" href="' + esc(fileUrl()) + '" download>' + (st === 'completed' ? 'تحميل النسخة النهائية (PDF)' : 'تحميل نسخة PDF') + '</a></div>'
      + '<div class="doc"><iframe id="docf" title="نص العقد" sandbox="allow-same-origin"></iframe></div>';
    var signable = st === 'verified' && S.approved;
    if (signable) {
      h += '<div class="read"><button class="btn ghost inline" id="readBtn" type="button">قرأت العقد</button></div>'
        + '<section class="card sign" id="signp" aria-labelledby="signT" hidden>'
        + '<h2 id="signT">التوقيع</h2>'
        + '<div class="fld"><label for="nm">اكتب اسمك الكامل كما في الهوية</label>'
        + '<input type="text" id="nm" autocomplete="name" placeholder="' + esc(S.signer) + '"></div>'
        + '<div class="fld"><label id="padL">ارسم توقيعك بإصبعك</label>'
        + '<div class="pad" id="pad"><canvas id="cv" role="img" aria-labelledby="padL"></canvas><div class="hint">وقّع هنا</div></div>'
        + '<div class="padrow"><span id="padMsg"></span><button class="link" id="clr" type="button">مسح</button></div></div>'
        + '<label class="consent"><input type="checkbox" id="ok"><span>قرأت العقد كاملاً وأوافق على جميع بنوده، وأقرّ بحجية التوقيع الإلكتروني وفق نظام التعاملات الإلكترونية</span></label>'
        + '<p class="msg" id="signMsg" role="alert"></p>'
        + '</section>';
    }
    put(greetingCard() + h);
    var f = $('docf');
    f.addEventListener('load', function () { fitFrame(f); trackReading(); });
    f.srcdoc = docHtml();
    if (signable) {
      cta(true, 'توقيع العقد', false);
      $('readBtn').onclick = function () { markRead(); var p = $('signp'); if (p) p.scrollIntoView({ behavior: 'smooth', block: 'start' }); };
      $('signBtn').onclick = submit;
      initPad();
      ['nm', 'ok'].forEach(function (id) { $(id).addEventListener('input', refresh); $(id).addEventListener('change', refresh); });
    } else if (st === 'completed' || st === 'signed_owner') {
      cta(true, st === 'completed' ? 'حفظ نسختي النهائية (PDF)' : 'حفظ نسختي (PDF)', true);
      $('signBtn').onclick = function () { location.href = fileUrl(); };
    } else {
      cta(true, 'التوقيع غير متاح — النموذج قيد المراجعة', false);
    }
  }

  function fitFrame(f) {
    try {
      var d = f.contentDocument;
      if (!d) return;
      var h = Math.max(d.documentElement.scrollHeight, d.body ? d.body.scrollHeight : 0);
      if (h > 0) f.style.height = (h + 8) + 'px';
      if (d.fonts && d.fonts.ready) d.fonts.ready.then(function () {
        var h2 = d.documentElement.scrollHeight; if (h2 > 0) f.style.height = (h2 + 8) + 'px';
      });
    } catch (_) { /* cross-origin fallback keeps the 70vh scroller */ }
  }

  function trackReading() {
    var onScroll = function () {
      var f = $('docf'); if (!f) return;
      var rect = f.getBoundingClientRect();
      var seen = (window.innerHeight - rect.top) / Math.max(1, rect.height);
      var p = Math.max(0, Math.min(1, seen));
      var bar = $('prog'); if (bar) bar.style.transform = 'scaleX(' + p.toFixed(3) + ')';
      if (p >= 0.95) markRead();
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    onScroll();
  }

  function markRead() {
    if (S.readOk) return;
    S.readOk = true;
    var p = $('signp'); if (p) p.hidden = false;
    var b = $('readBtn'); if (b && b.parentNode) b.parentNode.hidden = true;
    var bar = $('prog'); if (bar) bar.style.transform = 'scaleX(1)';
    if (S.pad) S.pad.resize();
    refresh();
  }

  /* ---------------- signature pad ---------------- */
  function initPad() {
    var cv = $('cv'), wrap = $('pad');
    var ctx = cv.getContext('2d');
    var drawing = false, last = null, length = 0, points = 0, dpr = 1;
    function resize() {
      var r = cv.getBoundingClientRect();
      if (!r.width) return;
      dpr = Math.max(1, Math.min(3, window.devicePixelRatio || 1));
      var keep = length > 0 ? cv.toDataURL('image/png') : null;
      cv.width = Math.round(r.width * dpr); cv.height = Math.round(r.height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.strokeStyle = '#1d2320'; ctx.lineWidth = 2.6;
      if (keep) { var im = new Image(); im.onload = function () { ctx.drawImage(im, 0, 0, r.width, r.height); }; im.src = keep; }
    }
    function pos(ev) { var r = cv.getBoundingClientRect(); return { x: ev.clientX - r.left, y: ev.clientY - r.top }; }
    cv.addEventListener('pointerdown', function (ev) {
      ev.preventDefault(); drawing = true; last = pos(ev);
      try { cv.setPointerCapture(ev.pointerId); } catch (_) {}
      ctx.beginPath(); ctx.arc(last.x, last.y, 1.2, 0, Math.PI * 2); ctx.fillStyle = '#1d2320'; ctx.fill();
      points++;
    });
    cv.addEventListener('pointermove', function (ev) {
      if (!drawing) return;
      ev.preventDefault();
      var p = pos(ev);
      ctx.beginPath(); ctx.moveTo(last.x, last.y); ctx.lineTo(p.x, p.y); ctx.stroke();
      length += Math.hypot(p.x - last.x, p.y - last.y); points++; last = p;
      wrap.classList.add('has');
    });
    function end() { if (drawing) { drawing = false; refresh(); } }
    cv.addEventListener('pointerup', end);
    cv.addEventListener('pointercancel', end);
    cv.addEventListener('pointerleave', end);
    $('clr').onclick = function () {
      ctx.clearRect(0, 0, cv.width, cv.height); length = 0; points = 0; wrap.classList.remove('has'); refresh();
    };
    window.addEventListener('resize', function () { if (!length) resize(); });
    S.pad = {
      resize: resize,
      ok: function () { return length >= 80 && points >= 12; },
      png: function () { return cv.toDataURL('image/png'); }
    };
    resize();
  }

  function refresh() {
    if (S.state !== 'verified') return;
    var nm = ($('nm') && $('nm').value || '').trim();
    var padOk = S.pad && S.pad.ok();
    var ready = S.readOk && nm.split(/ +/).length >= 2 && padOk && $('ok') && $('ok').checked;
    var pm = $('padMsg');
    if (pm) pm.textContent = (S.pad && !padOk && $('pad').classList.contains('has')) ? 'التوقيع قصير — كمّله' : '';
    cta(true, 'توقيع العقد', !!ready && !S.busy);
  }

  async function submit() {
    if (S.busy) return;
    S.busy = true;
    cta(true, 'جاري التوقيع…', false);
    $('signMsg').className = 'msg';
    $('signMsg').textContent = '';
    var r = await postJSON('/api/aqd-t/sign', {
      token: TOKEN, view_key: S.key, typed_name: ($('nm').value || '').trim(),
      consent: !!$('ok').checked, signature_png_b64: S.pad.png()
    });
    S.busy = false;
    if (!r || !r.ok) {
      if (r && r.reverify) { renderGate(); $('gateMsg').textContent = r.error; return; }
      if (r && r.state === 'signed_owner') { S.state = 'signed_owner'; return done(); }
      $('signMsg').className = 'msg bad';
      $('signMsg').textContent = (r && r.error) || 'ما قدرنا نحفظ التوقيع — جرّب مرة ثانية';
      refresh();
      return;
    }
    S.state = 'signed_owner';
    done();
  }

  function done() {
    put(stateCard('ok', 'تم التوقيع بنجاح — شكراً لثقتك',
      'بنرسل لك النسخة النهائية بعد توقيع عوجا على نفس الرابط.',
      '<a class="btn primary inline" style="display:inline-flex;align-items:center;justify-content:center;text-decoration:none" href="' + esc(fileUrl()) + '" download>حفظ نسختي (PDF)</a>'));
    cta(false);
    window.scrollTo(0, 0);
  }

  boot().catch(function () { showState('invalid', 'صار خطأ مؤقت — حدّث الصفحة وجرّب مرة ثانية'); });
})();
