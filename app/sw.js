// Service Worker — cache app shell + question banks for offline use.
// Bump CACHE_VERSION whenever shell files (HTML/CSS/JS) change so old caches roll over.
const CACHE_VERSION = 'iiqe-v1';
const SHELL = [
  './',
  './index.html',
  './css/style.css',
  './js/app.js',
  './data/_meta.js',
  './manifest.json',
  './icon.svg',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// Strategy:
//   - data/paperX.js  → cache-first, fall back to network (题库不变；省流量)
//   - shell files     → network-first, fall back to cache (能拿到新版就用新版)
//   - other (HTTPS)   → network-only
self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  const isPaperData = /\/data\/paper[^/]*\.js$/.test(url.pathname);
  if (isPaperData) {
    event.respondWith(
      caches.match(req).then((cached) => cached || fetch(req).then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE_VERSION).then((cache) => cache.put(req, copy));
        }
        return res;
      }))
    );
    return;
  }

  // Shell: network-first
  event.respondWith(
    fetch(req).then((res) => {
      if (res.ok) {
        const copy = res.clone();
        caches.open(CACHE_VERSION).then((cache) => cache.put(req, copy));
      }
      return res;
    }).catch(() => caches.match(req))
  );
});
