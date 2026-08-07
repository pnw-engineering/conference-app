const CACHE_NAME = "hbes-v1";
const ASSETS = [
  "./",
  "./index.html",
  "./manifest.json",
  "./icon-192.png",
  "./icon-512.png",
  "./bootstrap-icons.min.css",
  "./bootstrap.bundle.min.js",
  "./bootstrap.min.css",
  "./html5-qrcode.min.js",
  "./star.svg",
  "./star-fill.svg",
  "./x.svg",
  "./person.svg",
  "./calendar3.svg",
  "./calendar.svg",
  "./geo-alt.svg",
  "./qr-code-scan.svg",
  "./link-45deg.svg",
  "./share.svg",
  "./box-arrow-up.svg",
  "./map.svg"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS);
    }),
  );
});

self.addEventListener("fetch", (event) => {
  event.respondWith(
    caches.match(event.request).then((response) => {
      return (
        response ||
        fetch(event.request).catch(() => {
          if (event.request.mode === "navigate") {
            return caches.match("./index.html");
          }
        })
      );
    }),
  );
});

// Proactive Cache Cleanup Strategy
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cache) => {
          if (cache !== CACHE_NAME) {
            console.log("Clearing old cache:", cache);
            return caches.delete(cache);
          }
        }),
      );
    }),
  );
});
