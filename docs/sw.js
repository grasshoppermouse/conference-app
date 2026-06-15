const CACHE_NAME = "hbes2027-v1";
const ASSETS = [
  "./index.html",
  "./manifest.json",
  "./icon-192.png",
  "./icon-512.png",
  "./bootstrap-icons.min.css",
  "./bootstrap.bundle.min.js",
  "./bootstrap.min.css",
  "./fonts/bootstrap-icons.woff",
  "./fonts/bootstrap-icons.woff2",
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
      if (response) {
        return response;
      }
      // If not in cache, try the network
      return fetch(event.request).catch(() => {
        // Fallback for navigation requests if offline
        if (event.request.mode === "navigate") {
          return caches.match("./index.html");
        }
      });
    }),
  );
});
