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
 *   2. Navigations are CACHE-first. The shell is ~478KB brotli (5.9MB decoded)
 *      because the snapshot is inlined, and network-first meant paying that on
 *      every single app open even when nothing had changed. Freshness is instead
 *      driven by the page: it fetches the 369-byte deploy-manifest.json on every
 *      foreground, compares generated_at, and offers a reload when a newer
 *      snapshot exists. reloadSnapshot() in the page deletes the cached shell
 *      first, so that reload is a genuine network fetch — without that step
 *      cache-first would hand back the very copy the user is trying to replace.
 *   3. Same-origin static assets (icons, manifest), the Google Fonts CDN and the
 *      silk image CDN are cache-first — they are immutable enough that
 *      revalidating costs more than it saves, and the silks are what make an
 *      offline racecard actually readable.
 *   4. Anything else falls through to the network untouched.
 *
 * Bump CACHE_VERSION when the caching strategy changes (it purges old caches on
 * activate). Deploying new dashboard HTML does not need a bump — rule 2's
 * manifest check handles that.
 */

const CACHE_VERSION = "wongchoi-v2";
const PRECACHE = [
  "./",
  "./manifest.webmanifest",
  "./icon-180.png",
  "./icon-192.png",
  "./icon-512.png",
];

// Cross-origin hosts worth keeping offline. The silks are 18 images per racecard
// served from puntcdn; without them an offline racecard loses every colour cue.
const RUNTIME_CACHE_HOSTS = [
  "fonts.googleapis.com",
  "fonts.gstatic.com",
  "images.puntcdn.com",
];

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

  // Rule 2 — navigations: cache first. See the header comment for why, and for the
  // page-side manifest check that keeps this honest.
  if (request.mode === "navigate") {
    event.respondWith(
      (async () => {
        const cache = await caches.open(CACHE_VERSION);
        const hit = (await cache.match(request)) || (await cache.match("./"));
        if (hit) return hit;
        // Cold start, or reloadSnapshot() just evicted the shell on purpose.
        try {
          const response = await fetch(request);
          if (response.ok) cache.put(request, response.clone());
          return response;
        } catch {
          return new Response(
            "<meta charset=utf-8><h1>離線</h1><p>未有已快取嘅 Dashboard，請連上網絡再開一次。</p>",
            { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } },
          );
        }
      })(),
    );
    return;
  }

  // Rule 3 — immutable-ish static assets: cache first, populate on miss.
  const isStaticAsset =
    (sameOrigin && /\.(?:png|svg|ico|webmanifest|woff2?)$/.test(url.pathname)) ||
    RUNTIME_CACHE_HOSTS.includes(url.hostname);

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
