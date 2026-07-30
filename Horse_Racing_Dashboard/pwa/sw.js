/* 旺財 Dashboard — service worker.
 *
 * Purpose is narrow on purpose: make the installed app open without a network
 * (racecourse basements have no signal) WITHOUT ever serving stale betting or
 * ROI data.
 *
 * Rules, in priority order:
 *   1. /api/* is NEVER touched. Bet sync, portfolio, audit and settlement all
 *      have to hit the network or fail loudly — a cached POST/GET here would
 *      silently show wrong money.
 *   2. Navigations are network-first, cache-fallback. Online you always get the
 *      freshly deployed snapshot; offline you get the last one you loaded.
 *   3. Same-origin static assets (icons, manifest) and the Google Fonts CDN are
 *      cache-first — they are immutable enough that revalidating costs more
 *      than it saves.
 *   4. Anything else falls through to the network untouched.
 *
 * Bump CACHE_VERSION when the caching strategy changes. Deploying new dashboard
 * HTML does not need a bump — rule 2 already keeps it fresh.
 */

const CACHE_VERSION = "wongchoi-v1";
const PRECACHE = [
  "./",
  "./manifest.webmanifest",
  "./icon-180.png",
  "./icon-192.png",
  "./icon-512.png",
];

const FONT_HOSTS = ["fonts.googleapis.com", "fonts.gstatic.com"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_VERSION)
      // addAll() is atomic — one 404 would throw away the whole precache, and a
      // failed install means no offline support at all. Cache what we can.
      .then((cache) => Promise.allSettled(PRECACHE.map((url) => cache.add(url))))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== CACHE_VERSION).map((key) => caches.delete(key))),
      )
      // Take over open tabs right away. On a data dashboard, waiting for every
      // tab to close before an update applies is worse than the alternative.
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  const sameOrigin = url.origin === self.location.origin;

  // Rule 1 — never cache or shortcut the live APIs.
  if (sameOrigin && url.pathname.startsWith("/api/")) return;

  // Rule 2 — navigations: network first, fall back to the last good copy.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_VERSION).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(async () => {
          const cache = await caches.open(CACHE_VERSION);
          return (
            (await cache.match(request)) ||
            (await cache.match("./")) ||
            new Response(
              "<meta charset=utf-8><h1>離線</h1><p>未有已快取嘅 Dashboard，請連上網絡再開一次。</p>",
              { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } },
            )
          );
        }),
    );
    return;
  }

  // Rule 3 — immutable-ish static assets: cache first, populate on miss.
  const isStaticAsset =
    (sameOrigin && /\.(?:png|svg|ico|webmanifest|woff2?)$/.test(url.pathname)) ||
    FONT_HOSTS.includes(url.hostname);

  if (isStaticAsset) {
    event.respondWith(
      caches.match(request).then(
        (hit) =>
          hit ||
          fetch(request).then((response) => {
            // Opaque cross-origin font responses are still worth storing; only
            // skip genuine same-origin errors.
            if (response.ok || response.type === "opaque") {
              const copy = response.clone();
              caches.open(CACHE_VERSION).then((cache) => cache.put(request, copy));
            }
            return response;
          }),
      ),
    );
  }

  // Rule 4 — everything else: no interception.
});
