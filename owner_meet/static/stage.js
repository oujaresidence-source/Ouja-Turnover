/* «اجتماع المالك» — the shared presentation stage.
 *
 * Served at /meet/static/stage.js by owner_meet/routes.py. The slides are server-rendered from the
 * frozen snapshot; this file only moves between them. It is a real file on purpose (no Python string
 * eats its backslashes) and must pass `node --check`.
 *
 * Keys (RTL): ArrowLeft / PageDown / Space = next, ArrowRight / PageUp = previous, Home / End,
 * F = full screen, B = black screen, N = open the presenter window (never shared).
 * Sync: BroadcastChannel to the presenter window in the same browser; a short-poll cursor on the
 * server for a presenter on a phone. The stage is the source of truth.
 */
(function () {
  'use strict';
  var stage = document.getElementById('stage');
  if (!stage) return;
  var slides = Array.prototype.slice.call(stage.querySelectorAll('.slide'));
  var total = slides.length;
  var mid = stage.getAttribute('data-meeting');
  var prog = document.getElementById('prog');
  var black = document.getElementById('black');
  var cur = 0;
  var seenSeq = 0;
  var bc = null;
  try { bc = new BroadcastChannel('ouja-meet-' + mid); } catch (e) { bc = null; }

  slides.forEach(function (s, i) {
    var pg = s.querySelector('.pg');
    if (pg) pg.textContent = (i + 1) + ' / ' + total;
  });

  var pushTimer = null;
  function push() {
    clearTimeout(pushTimer);
    pushTimer = setTimeout(function () {
      fetch('/api/meet/meetings/' + mid + '/cursor', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ i: cur, by: 'stage' })
      }).then(function (r) { return r.json(); }).then(function (d) {
        if (d && d.seq) seenSeq = d.seq;
      }).catch(function () {});
    }, 160);
  }

  function show(i, from) {
    i = Math.max(0, Math.min(total - 1, i));
    if (i !== cur) {
      slides[cur].classList.remove('on');
      cur = i;
      slides[cur].classList.add('on');
    }
    if (prog) prog.style.transform = 'scaleX(' + ((cur + 1) / total) + ')';
    if (from !== 'bc' && bc) bc.postMessage({ t: 'at', i: cur });
    if (from !== 'poll') push();
    try { history.replaceState(null, '', '#' + (cur + 1)); } catch (e) {}
  }

  function toggleBlack() { if (black) black.hidden = !black.hidden; }

  function fullScreen() {
    var el = document.documentElement;
    if (document.fullscreenElement) { document.exitFullscreen().catch(function () {}); }
    else if (el.requestFullscreen) { el.requestFullscreen().catch(function () {}); }
  }

  function openNotes() {
    window.open('/meet/' + mid + '/notes', 'ouja-meet-notes-' + mid, 'width=760,height=900');
  }

  document.addEventListener('keydown', function (e) {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    var k = e.key;
    if (k === 'ArrowLeft' || k === 'PageDown' || k === ' ') { e.preventDefault(); show(cur + 1); }
    else if (k === 'ArrowRight' || k === 'PageUp') { e.preventDefault(); show(cur - 1); }
    else if (k === 'Home') { e.preventDefault(); show(0); }
    else if (k === 'End') { e.preventDefault(); show(total - 1); }
    else if (k === 'f' || k === 'F') { fullScreen(); }
    else if (k === 'b' || k === 'B' || k === '.') { toggleBlack(); }
    else if (k === 'n' || k === 'N') { openNotes(); }
  });
  if (black) black.addEventListener('click', toggleBlack);

  if (bc) {
    bc.onmessage = function (ev) {
      var m = ev.data || {};
      if (m.t === 'step') show(cur + (m.d || 0), 'bc');
      else if (m.t === 'go') show(m.i || 0, 'bc');
      else if (m.t === 'hello') bc.postMessage({ t: 'at', i: cur });
      if (m.t === 'step' || m.t === 'go') bc.postMessage({ t: 'at', i: cur });
    };
  }

  /* A presenter on a phone has no BroadcastChannel to this tab: it writes the server cursor and
     the stage follows any NEWER cursor written by the notes side. */
  setInterval(function () {
    if (document.hidden) return;
    fetch('/api/meet/meetings/' + mid + '/cursor', { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d && d.ok && d.by === 'notes' && d.seq > seenSeq) { seenSeq = d.seq; show(d.i, 'poll'); push(); }
      }).catch(function () {});
  }, 2000);

  function fromHash() {
    var n = parseInt((location.hash || '').slice(1), 10);
    return isFinite(n) && n > 0 ? n - 1 : 0;
  }
  window.addEventListener('hashchange', function () { if (fromHash() !== cur) show(fromHash()); });
  show(fromHash(), 'init');
})();
