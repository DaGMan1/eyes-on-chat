// eyes-on-chat service worker — installability + push notifications.
// Deliberately no offline caching: this is an actively-developed chat app,
// stale cached JS/HTML would be a worse bug than "no offline mode."

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

// A no-op fetch handler is required by some browsers' installability
// criteria even though we don't intercept anything.
self.addEventListener("fetch", () => {});

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { title: "eyes-on-chat", body: event.data ? event.data.text() : "New message" };
  }
  const title = data.title || "eyes-on-chat";
  const options = {
    body: data.body || "New message",
    icon: "/static/icons/icon-192.png",
    badge: "/static/icons/icon-192.png",
    data: { url: data.url || "/chat/" },
    tag: data.session_id || "eyes-on-chat",
    renotify: true,
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/chat/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if (client.url.includes(url) && "focus" in client) return client.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow(url);
    })
  );
});
