/* Ouja Finance ERP v2 — front-end.
   Phase 0: prove the static pipeline + API loop work end-to-end:
   this file is served from /erp/static/, calls /erp/version, and confirms the
   live server build matches the HTML the server stamped. */
(function () {
  'use strict';

  var el = document.getElementById('liveCheck');
  if (!el) return;

  fetch('/erp/version')
    .then(function (r) { return r.json(); })
    .then(function (v) {
      var stamped = (window.__ERP_BUILD__ || {});
      if (v && v.ok && v.version === stamped.version) {
        el.textContent = 'الخادم متصل ✓ ' + v.version;
        el.className = 'boot-check ok';
      } else {
        el.textContent = 'نسخة الخادم مختلفة: ' + (v && v.version);
        el.className = 'boot-check bad';
      }
    })
    .catch(function () {
      el.textContent = 'تعذر الوصول للخادم';
      el.className = 'boot-check bad';
    });
})();
