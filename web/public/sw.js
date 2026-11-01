/*
 * The crew's service worker, for one thing only: showing what the server pushes and opening
 * the app where the notification points. It has no fetch handler, so it caches nothing and
 * every request goes to the network as it would without it.
 *
 * A push always shows a notification: a browser withdraws the subscription of a page that
 * receives pushes and shows none (Safari after very few).
 */

const FALLBACK = { title: "my-agent-crew", body: "", url: "/#/inbox", tag: "crew" };

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let notice = FALLBACK;
  try {
    notice = { ...FALLBACK, ...(event.data ? event.data.json() : {}) };
  } catch {
    // A body that is not the server's JSON still shows the fallback.
  }
  event.waitUntil(
    self.registration.showNotification(notice.title, {
      body: notice.body,
      tag: notice.tag,
      // A second notice of the same kind replaces the first and still buzzes.
      renotify: true,
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      data: { url: notice.url },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || "/#/inbox", self.location.origin).href;
  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      const open = windows.find((client) => new URL(client.url).origin === self.location.origin);
      if (open) {
        // The page moves to the hash itself (`lib/push.ts`): a navigation would reload it.
        open.postMessage({ type: "crew-open", url: target });
        await open.focus();
        return;
      }
      await self.clients.openWindow(target);
    })(),
  );
});
