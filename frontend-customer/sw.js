// Same shape as the instructor app's sw.js — see that file's comment for
// why API calls are excluded from caching. Paths are prefixed with
// /customer/ since this service worker's scope is that mount, not root.
const CACHE_NAME = 'attune-customer-v1';
const SHELL = ['/customer/', '/customer/index.html', '/customer/style.css', '/customer/app.js', '/customer/manifest.json', '/customer/icon-192.png', '/customer/icon-512.png'];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  if (new URL(event.request.url).pathname.startsWith('/api/')) return;
  event.respondWith(caches.match(event.request).then((cached) => cached || fetch(event.request)));
});
