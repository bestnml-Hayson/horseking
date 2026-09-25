/* ==========================================================
   Service Worker 賽馬 AI Live - PWA 離線快取
   Cache Strategy: Network First (HTML / Data), Cache First (CSS/JS/Img)
   ========================================================== */

const CACHE_VERSION = 'horse-ai-v2.0.16-openHorseDetail-TDZ-fix';
const DATA_CACHE = 'horse-ai-data-v2.0.16-openHorseDetail-TDZ-fix';
const APP_SHELL = [
  '/',
  '/index.html',
  '/manifest.webmanifest',
  '/style.css',
  '/ai.js',
  '/app.js',
  '/data/icons/icon-192.png',
  '/data/icons/icon-512.png'
];

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE_VERSION).then(function (cache) {
      return cache.addAll(APP_SHELL).catch(function () {
        return cache.addAll(['/', '/index.html', '/style.css', '/ai.js', '/app.js']);
      });
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (k) {
        return k !== CACHE_VERSION && k !== DATA_CACHE;
      }).map(function (k) { return caches.delete(k); }));
    }).then(function () {
      return self.clients.claim();
    })
  );
});

function isAssetRequest(u) {
  return /\.(css|js|png|jpg|jpeg|svg|ico|woff2?|ttf|webp|gif)$/i.test(u);
}
function isDataRequest(u) {
  return /\/data\/|\/api\//.test(u) && /\.json$/i.test(u);
}

self.addEventListener('fetch', function (event) {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // 1. Static Assets (CSS/JS/IMG): Cache First
  if (isAssetRequest(url.pathname)) {
    event.respondWith(
      caches.match(req).then(function (cached) {
        if (cached) return cached;
        return fetch(req).then(function (resp) {
          const copy = resp.clone();
          caches.open(CACHE_VERSION).then(function (c) { c.put(req, copy).catch(function () {}); });
          return resp;
        }).catch(function () { return cached; });
      })
    );
    return;
  }

  // 2. Data JSON: Network First, Stale-While-Revalidate
  if (isDataRequest(url.pathname)) {
    event.respondWith(
      caches.open(DATA_CACHE).then(function (cache) {
        return fetch(req).then(function (resp) {
          cache.put(req, resp.clone()).catch(function () {});
          return resp;
        }).catch(function () {
          return cache.match(req).then(function (cached) {
            return cached || new Response(JSON.stringify({ error: 'offline' }), {
              status: 503,
              headers: { 'Content-Type': 'application/json' }
            });
          });
        });
      })
    );
    return;
  }

  // 3. HTML: Network First with offline fallback
  event.respondWith(
    fetch(req).then(function (resp) {
      const copy = resp.clone();
      caches.open(CACHE_VERSION).then(function (c) { c.put(req, copy).catch(function () {}); });
      return resp;
    }).catch(function () {
      return caches.match(req).then(function (cached) {
        return cached || caches.match('/index.html');
      });
    })
  );
});
