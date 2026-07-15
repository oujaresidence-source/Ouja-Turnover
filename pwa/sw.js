/*
 * Ouja Operations — Service Worker
 * -------------------------------------------------------------
 * Caching contract (deliberate — this app shows LIVE Hostaway data):
 *   • /api/**  and  /erp/api/**   → NEVER cached. Pure network pass-through.
 *                                    Live operational data is never served stale.
 *   • HTML navigations             → NETWORK-FIRST. Online users always get the
 *                                    freshest build; cache is only an offline
 *                                    fallback so the app still opens with no signal.
 *   • Static, versioned assets      → CACHE-FIRST (stale-while-revalidate):
 *     (/pwa/**, /erp/static/**,       instant load, refreshed quietly in the
 *      images/fonts/css/js)           background.
 *
 * Update mechanism: a new deploy ships a new sw.js. It installs in the
 * background, then the page shows a small "تحديث" prompt. Tapping it posts
 * SKIP_WAITING → the new SW activates → the page reloads once with the new
 * build. Users never get stuck on a stale cached version.
 */
const VERSION = 'ouja-v1';
const STATIC_CACHE = 'ouja-static-' + VERSION;
const SHELL_CACHE = 'ouja-shell-' + VERSION;

// Small, safe precache. HTML is intentionally NOT precached (network-first).
const PRECACHE = [
  '/manifest.webmanifest',
  '/pwa/icons/icon-192.png',
  '/pwa/icons/icon-512.png',
  '/pwa/icons/apple-touch-icon.png'
];

const OFFLINE_HTML =
  '<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">' +
  '<meta name="viewport" content="width=device-width,initial-scale=1">' +
  '<title>عوجا — غير متصل</title><style>' +
  'html,body{height:100%;margin:0}body{display:flex;align-items:center;justify-content:center;' +
  'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;' +
  'background:#0E0D0C;color:#F4EFE5;text-align:center;padding:24px}' +
  '.c{max-width:340px}.m{font-size:56px;color:#D4A854;font-weight:700;margin-bottom:14px}' +
  'h1{font-size:20px;margin:0 0 8px}p{color:#A89E8D;font-size:14px;line-height:1.7;margin:0 0 20px}' +
  'button{background:#D4A854;color:#161310;border:0;border-radius:12px;padding:12px 22px;' +
  'font-size:15px;font-weight:700;cursor:pointer}</style></head><body><div class="c">' +
  '<div class="m">ع</div><h1>لا يوجد اتصال بالإنترنت</h1>' +
  '<p>تحتاج اتصالاً بالشبكة لعرض بيانات عوجا المباشرة. تأكد من الاتصال وحاول مرة أخرى.</p>' +
  '<button onclick="location.reload()">إعادة المحاولة</button></div></body></html>';

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((c) => c.addAll(PRECACHE)).catch(() => {})
  );
  // Do NOT skipWaiting here — wait for the page to confirm the update.
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(
      keys.filter((k) => k.indexOf('ouja-') === 0 &&
                         k !== STATIC_CACHE && k !== SHELL_CACHE)
          .map((k) => caches.delete(k))
    );
    await self.clients.claim();
  })());
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
});

function isApi(url) {
  return url.pathname.indexOf('/api/') !== -1; // covers /api/** and /erp/api/**
}
function isStaticAsset(url) {
  if (url.pathname.indexOf('/pwa/') === 0) return true;
  if (url.pathname.indexOf('/erp/static/') === 0) return true;
  return /\.(?:png|jpg|jpeg|webp|gif|svg|ico|woff2?|ttf|otf|css|js)$/i.test(url.pathname);
}

// Network-first, cache fallback — for HTML navigations only.
async function networkFirstShell(request) {
  try {
    const fresh = await fetch(request);
    if (fresh && fresh.ok && fresh.type === 'basic') {
      const copy = fresh.clone();
      caches.open(SHELL_CACHE).then((c) => c.put(request, copy)).catch(() => {});
    }
    return fresh;
  } catch (_) {
    const cached = await caches.match(request, { ignoreSearch: true });
    if (cached) return cached;
    return new Response(OFFLINE_HTML, {
      headers: { 'Content-Type': 'text/html; charset=utf-8' }
    });
  }
}

// Cache-first + background refresh — for static, versioned assets.
async function staleWhileRevalidate(request) {
  const cache = await caches.open(STATIC_CACHE);
  const cached = await cache.match(request);
  const network = fetch(request).then((resp) => {
    if (resp && (resp.ok || resp.type === 'opaque')) {
      cache.put(request, resp.clone()).catch(() => {});
    }
    return resp;
  }).catch(() => null);
  return cached || network || fetch(request);
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;

  let url;
  try { url = new URL(request.url); } catch (_) { return; }

  // Only manage our own origin; leave cross-origin (Google Fonts, etc.) to the browser.
  if (url.origin !== self.location.origin) return;

  // Live data — never touched by the cache.
  if (isApi(url)) return;

  // HTML navigations — always try the network first.
  if (request.mode === 'navigate' ||
      (request.headers.get('accept') || '').indexOf('text/html') !== -1) {
    event.respondWith(networkFirstShell(request));
    return;
  }

  // Static assets — fast from cache, refreshed in the background.
  if (isStaticAsset(url)) {
    event.respondWith(staleWhileRevalidate(request));
  }
});
