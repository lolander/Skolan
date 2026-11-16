// Skolans service worker: bara notiser (ingen offline-cache, allt hämtas från familjens dator).
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (err) { d = { body: e.data && e.data.text() }; }
  e.waitUntil(self.registration.showNotification(d.title || "Skolan", {
    body: d.body || "", icon: "/app/bilder/ikon-192.png", badge: "/app/bilder/ikon-64.png",
    image: d.image || undefined, tag: d.tag || undefined, data: { url: d.url || "/skolan" },
  }));
});
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = new URL(e.notification.data?.url || "/skolan", self.location.origin).href;
  e.waitUntil((async () => {
    const lista = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const c of lista) { if ("navigate" in c) { await c.navigate(url); return c.focus(); } }
    return self.clients.openWindow(url);
  })());
});
