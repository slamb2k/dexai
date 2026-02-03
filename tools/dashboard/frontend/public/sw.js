/**
 * DexAI Service Worker
 *
 * Handles:
 * - Push notification events
 * - Notification clicks
 * - Background sync (future)
 *
 * ADHD-Friendly Design:
 * - Clear, supportive notification messages
 * - Single action per notification
 * - Proper notification grouping
 */

// Service Worker Version
const SW_VERSION = '1.0.0';

// Cache name for offline support
const CACHE_NAME = `dexai-cache-v${SW_VERSION}`;

// API base URL (injected during build or fallback)
const API_URL = self.location.origin;

// =============================================================================
// Push Event Handler
// =============================================================================

self.addEventListener('push', (event) => {
  console.log('[SW] Push event received');

  if (!event.data) {
    console.log('[SW] Push event has no data');
    return;
  }

  let data;
  try {
    data = event.data.json();
  } catch (e) {
    console.error('[SW] Failed to parse push data:', e);
    return;
  }

  const {
    title = 'DexAI',
    body = '',
    icon = '/icons/dex-192.png',
    badge = '/icons/badge-72.png',
    data: notificationData = {},
    tag,
    requireInteraction = false,
    silent = false,
    actions = [],
    renotify = false,
  } = data;

  // Build notification options
  const options = {
    body,
    icon,
    badge,
    data: {
      ...notificationData,
      timestamp: Date.now(),
    },
    tag: tag || `dexai-${Date.now()}`,
    requireInteraction,
    silent,
    renotify,
    // Only include actions if provided
    ...(actions.length > 0 && { actions }),
  };

  // Track delivery
  const notificationId = notificationData?.notification_id;
  if (notificationId) {
    trackDelivery(notificationId).catch(console.error);
  }

  event.waitUntil(
    self.registration.showNotification(title, options)
  );
});

// =============================================================================
// Notification Click Handler
// =============================================================================

self.addEventListener('notificationclick', (event) => {
  console.log('[SW] Notification clicked');

  const notification = event.notification;
  const notificationData = notification.data || {};
  const actionUrl = notificationData.action_url || '/';
  const notificationId = notificationData.notification_id;

  // Close the notification
  notification.close();

  // Track click
  if (notificationId) {
    trackClick(notificationId).catch(console.error);
  }

  // Handle action button clicks
  if (event.action) {
    console.log('[SW] Action clicked:', event.action);
    // Handle specific actions if needed
  }

  // Focus or open window
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clientList) => {
        // Try to find an existing window to focus
        for (const client of clientList) {
          if (client.url.includes(self.location.origin) && 'focus' in client) {
            // Navigate existing window
            if (actionUrl !== '/') {
              client.navigate(actionUrl);
            }
            return client.focus();
          }
        }
        // No existing window, open new one
        return clients.openWindow(actionUrl);
      })
  );
});

// =============================================================================
// Notification Close Handler (dismissed without click)
// =============================================================================

self.addEventListener('notificationclose', (event) => {
  console.log('[SW] Notification dismissed');

  const notificationData = event.notification.data || {};
  const notificationId = notificationData.notification_id;

  if (notificationId) {
    trackDismiss(notificationId).catch(console.error);
  }
});

// =============================================================================
// Tracking Functions
// =============================================================================

async function trackDelivery(notificationId) {
  try {
    await fetch(`${API_URL}/api/push/track/delivered?notification_id=${notificationId}`, {
      method: 'POST',
      credentials: 'include',
    });
  } catch (e) {
    console.error('[SW] Failed to track delivery:', e);
  }
}

async function trackClick(notificationId) {
  try {
    await fetch(`${API_URL}/api/push/track/clicked?notification_id=${notificationId}`, {
      method: 'POST',
      credentials: 'include',
    });
  } catch (e) {
    console.error('[SW] Failed to track click:', e);
  }
}

async function trackDismiss(notificationId) {
  try {
    await fetch(`${API_URL}/api/push/track/dismissed?notification_id=${notificationId}`, {
      method: 'POST',
      credentials: 'include',
    });
  } catch (e) {
    console.error('[SW] Failed to track dismiss:', e);
  }
}

// =============================================================================
// Service Worker Lifecycle
// =============================================================================

self.addEventListener('install', (event) => {
  console.log('[SW] Installing service worker v' + SW_VERSION);
  // Skip waiting to activate immediately
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  console.log('[SW] Activating service worker v' + SW_VERSION);

  event.waitUntil(
    // Clean up old caches
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name.startsWith('dexai-') && name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    }).then(() => {
      // Take control of all clients
      return self.clients.claim();
    })
  );
});

// =============================================================================
// Background Sync (for future offline support)
// =============================================================================

self.addEventListener('sync', (event) => {
  console.log('[SW] Background sync:', event.tag);

  if (event.tag === 'notification-sync') {
    // Future: sync notification preferences when back online
  }
});

// =============================================================================
// Message Handler (for communication with main app)
// =============================================================================

self.addEventListener('message', (event) => {
  console.log('[SW] Message received:', event.data);

  const { type, payload } = event.data || {};

  switch (type) {
    case 'SKIP_WAITING':
      self.skipWaiting();
      break;

    case 'GET_VERSION':
      event.ports[0].postMessage({ version: SW_VERSION });
      break;

    default:
      console.log('[SW] Unknown message type:', type);
  }
});
