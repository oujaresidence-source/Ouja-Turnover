/* «اجتماع المالك» — the presenter window (never shared).
 *
 * Served at /meet/static/notes.js. Follows the stage through BroadcastChannel when both windows are
 * in the same browser, and through the server cursor (2 s poll) when it is open on a phone. The
 * buttons and arrow keys drive the stage from here. Must pass `node --check`.
 */
(function () {
  'use strict';
  var box = document.getElementById('cards');
  if (!box) return;
  var mid = box.getAttribute('data-meeting');
  var total = parseInt(box.getAttribute('data-total'), 10) || 1;
  var cards = Array.prototype.slice.call(box.querySelectorAll('.nt-card'));
  var cur = 0;
  var lastBc = 0;
  var bc = null;
  try { bc = new BroadcastChannel('ouja-meet-' + mid); } catch (e) { bc = null; }

  function paint(i) {
    i = Math.max(0, Math.min(total - 1, i));
    if (cards[cur]) cards[cur].classList.remove('on');
    cur = i;
    if (cards[cur]) cards[cur].classList.add('on');
    var j = document.getElementById('jump');
    if (j) {
      var best = null;
      Array.prototype.forEach.call(j.options, function (o) { if (parseInt(o.value, 10) <= cur) best = o.value; });
      if (best !== null) j.value = best;
    }
  }

  function go(i) {
    i = Math.max(0, Math.min(total - 1, i));
    paint(i);
    if (bc) bc.postMessage({ t: 'go', i: i });
    fetch('/api/meet/meetings/' + mid + '/cursor', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ i: i, by: 'notes' })
    }).catch(function () {});
  }

  document.addEventListener('click', function (e) {
    var b = e.target.closest ? e.target.closest('[data-go]') : null;
    if (b) go(cur + parseInt(b.getAttribute('data-go'), 10));
  });
  var jump = document.getElementById('jump');
  if (jump) jump.addEventListener('change', function () { go(parseInt(jump.value, 10)); });
  document.addEventListener('keydown', function (e) {
    if (e.target && e.target.tagName === 'SELECT') return;
    if (e.key === 'ArrowLeft' || e.key === 'PageDown' || e.key === ' ') { e.preventDefault(); go(cur + 1); }
    else if (e.key === 'ArrowRight' || e.key === 'PageUp') { e.preventDefault(); go(cur - 1); }
  });

  if (bc) {
    bc.onmessage = function (ev) {
      var m = ev.data || {};
      if (m.t === 'at') { lastBc = Date.now(); paint(m.i || 0); }
    };
    bc.postMessage({ t: 'hello' });
  }

  setInterval(function () {
    if (Date.now() - lastBc < 5000) return;
    fetch('/api/meet/meetings/' + mid + '/cursor', { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) { if (d && d.ok && d.by === 'stage') paint(d.i || 0); })
      .catch(function () {});
  }, 2000);

  var t0 = Date.now();
  var clock = document.getElementById('clock');
  setInterval(function () {
    var s = Math.floor((Date.now() - t0) / 1000);
    var mm = Math.floor(s / 60), ss = s % 60;
    if (clock) clock.textContent = (mm < 10 ? '0' : '') + mm + ':' + (ss < 10 ? '0' : '') + ss;
  }, 1000);
})();

/* The meeting record: decisions and commitments, saved the moment they are added. */
(function () {
  'use strict';
  var box = document.getElementById('cards');
  var rec = document.getElementById('rec');
  if (!box || !rec) return;
  var mid = box.getAttribute('data-meeting');
  var base = '/api/meet/meetings/' + mid;
  var SIDE = { decision: 'قرار', ouja: 'علينا', owner: 'على المالك' };
  var MONTHS = ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'];
  function day(iso) {
    var m = /^([0-9]{4})-([0-9]{2})-([0-9]{2})/.exec(String(iso || ''));
    return m ? (parseInt(m[3], 10) + ' ' + MONTHS[parseInt(m[2], 10) - 1] + ' ' + m[1]) : '';
  }

  function esc(x) {
    return String(x == null ? '' : x).replace(/[<>&"']/g, function (c) {
      return { '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function msg(t) { var m = document.getElementById('recMsg'); if (m) m.textContent = t || ''; }
  function call(path, body) {
    return fetch(base + path, {
      method: body ? 'POST' : 'GET', credentials: 'same-origin',
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined
    }).then(function (r) { return r.json(); });
  }
  function paint(r) {
    var ul = document.getElementById('recList');
    if (!ul || !r) return;
    var rows = (r.decisions || []).map(function (d) { return { kind: 'decision', id: d.id, text: d.text, extra: d.amount_sar ? (d.amount_sar + ' ريال') : '' }; })
      .concat((r.commitments || []).map(function (c) { return { kind: c.side, id: c.id, text: c.text, extra: c.due ? ('بحلول ' + day(c.due)) : '' }; }));
    ul.innerHTML = rows.map(function (x) {
      return '<li><div><span>' + SIDE[x.kind] + '</span>' + esc(x.text) + (x.extra ? ' · ' + esc(x.extra) : '') + '</div>' +
        '<button type="button" data-del="' + (x.kind === 'decision' ? 'decision' : 'commitment') + '" data-id="' + x.id + '">حذف</button></li>';
    }).join('') || '<li><div>لا شيء مسجّل بعد.</div></li>';
  }
  rec.addEventListener('submit', function (e) {
    var f = e.target.closest('form.rf');
    if (!f) return;
    e.preventDefault();
    var body = { kind: f.getAttribute('data-kind') };
    Array.prototype.forEach.call(f.elements, function (el) { if (el.name) body[el.name] = el.value; });
    call('/record', body).then(function (r) {
      if (r && r.ok) { f.reset(); paint(r.record); msg('حُفظ.'); } else { msg((r && r.error_ar) || 'تعذّر الحفظ'); }
    }).catch(function () { msg('تعذّر الحفظ'); });
  });
  rec.addEventListener('click', function (e) {
    var b = e.target.closest ? e.target.closest('[data-del],[data-presented]') : null;
    if (!b) return;
    if (b.hasAttribute('data-presented')) {
      call('/presented', {}).then(function () { msg('سُجّل الاجتماع كمنتهٍ. الإرسال للمالك من تبويب «اجتماع المالك».'); });
      return;
    }
    call('/record/delete', { kind: b.getAttribute('data-del'), id: b.getAttribute('data-id') }).then(function (r) {
      if (r && r.ok) { paint(r.record); msg('حُذف.'); } else { msg((r && r.error_ar) || 'تعذّر الحذف'); }
    });
  });
  call('/record').then(function (r) { if (r && r.ok) paint(r.record); }).catch(function () {});
})();
