self.addEventListener('install', e => e.waitUntil(self.skipWaiting()));
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));

self.addEventListener('fetch', e => e.respondWith(
    fetch(e.request).catch(() => caches.match(e.request))
));

// Push notifications
self.addEventListener('push', e => {
    let data = { title: 'TaskRemind', body: 'You have reminders!' };
    try { data = e.data.json(); } catch(_) {}
    const opts = {
        body: data.body,
        icon: '/static/icon-192.png',
        badge: '/static/icon-192.png',
        tag: 'taskremind-' + Date.now(),
        requireInteraction: true
    };
    e.waitUntil(self.registration.showNotification(data.title, opts));
});

self.addEventListener('notificationclick', e => {
    e.notification.close();
    e.waitUntil(clients.openWindow('/'));
});
