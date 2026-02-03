# Phase 10: Mobile Push Notifications — Tactical Implementation Guide

**Status:** ✅ Complete (10a + 10b)
**Depends on:** Phase 0 (Security), Phase 4 (Smart Notifications), Phase 7 (Dashboard)
**Last Updated:** 2026-02-04

---

## Overview

Phase 10 extends DexAI's notification system to mobile devices via push notifications. The system respects ADHD users' flow states, batches notifications intelligently, and provides granular control over what interrupts are worth the cognitive cost.

**Key Innovation:** Unlike typical push notification systems that maximize engagement through interruption, DexAI's mobile push is designed to **minimize unnecessary interruptions** while ensuring truly important things get through.

---

## Architecture Decision: Progressive Enhancement

Rather than building a full native app immediately, we use a **progressive enhancement** approach:

| Phase | Approach | Coverage | Effort |
|-------|----------|----------|--------|
| **10a** | Web Push (PWA) | Chrome, Edge, Firefox, Android | Low |
| **10b** | Expo Wrapper | iOS + Enhanced Android | Medium |
| **10c** | Native Features | Background sync, widgets | High |

**Rationale:** Web Push covers ~70% of use cases with minimal development. iOS requires a native wrapper due to Safari limitations, added in 10b.

---

## Sub-Phases

| Sub-Phase | Focus | Status |
|-----------|-------|--------|
| **10a** | Web Push + PWA | ✅ Complete |
| **10b** | Expo Mobile Wrapper (iOS) | ✅ Complete |
| **10c** | Native Enhancements | 📋 Planned |

---

## Phase 10a: Web Push + PWA

### Objective

Implement Web Push notifications for the dashboard PWA, providing mobile notifications on Android and desktop browsers without an app store deployment.

### Directory Structure

```
tools/mobile/
├── __init__.py                    # Path constants, shared utilities
├── models.py                      # PushSubscription, Notification, DeviceToken
│
├── push/
│   ├── __init__.py
│   ├── web_push.py                # VAPID-based Web Push (pywebpush)
│   ├── subscription_manager.py   # Store/retrieve push subscriptions
│   ├── notification_builder.py   # Build notification payloads
│   └── delivery.py               # Send notifications with retry logic
│
├── queue/
│   ├── __init__.py
│   ├── notification_queue.py     # Priority queue for pending notifications
│   ├── batcher.py                # Batch related notifications
│   └── scheduler.py              # Timing logic (quiet hours, flow state)
│
├── preferences/
│   ├── __init__.py
│   ├── user_preferences.py       # Per-user notification settings
│   └── category_manager.py       # Notification categories and priorities
│
└── analytics/
    ├── __init__.py
    └── delivery_tracker.py       # Track delivery, open rates, dismissals
```

### Database Schema

```sql
-- Push subscriptions (Web Push endpoints)
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    endpoint TEXT NOT NULL UNIQUE,        -- Web Push endpoint URL
    p256dh_key TEXT NOT NULL,             -- Client public key
    auth_key TEXT NOT NULL,               -- Auth secret
    device_name TEXT,                     -- User-provided device name
    device_type TEXT,                     -- 'web', 'android', 'ios'
    browser TEXT,                         -- 'chrome', 'firefox', 'safari', 'edge'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_used_at DATETIME,
    is_active BOOLEAN DEFAULT TRUE
);

-- Notification queue
CREATE TABLE IF NOT EXISTS notification_queue (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    category TEXT NOT NULL,               -- 'task', 'reminder', 'message', 'system'
    priority INTEGER DEFAULT 5,           -- 1-10 (10 = highest)
    title TEXT NOT NULL,
    body TEXT,
    data TEXT,                            -- JSON payload for click actions
    icon_url TEXT,
    action_url TEXT,                      -- URL to open on click

    -- Scheduling
    scheduled_for DATETIME,               -- NULL = send immediately
    expires_at DATETIME,                  -- Don't send after this time

    -- Batching
    batch_key TEXT,                       -- Group related notifications
    batch_window_seconds INTEGER DEFAULT 300,

    -- Status
    status TEXT DEFAULT 'pending',        -- 'pending', 'sent', 'delivered', 'failed', 'batched', 'suppressed'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    sent_at DATETIME,

    -- Flow state check
    respect_flow_state BOOLEAN DEFAULT TRUE,
    min_priority_to_interrupt INTEGER DEFAULT 8  -- Only interrupt flow for priority >= this
);

-- Notification delivery log
CREATE TABLE IF NOT EXISTS notification_delivery_log (
    id TEXT PRIMARY KEY,
    notification_id TEXT NOT NULL,
    subscription_id TEXT NOT NULL,
    status TEXT NOT NULL,                 -- 'sent', 'delivered', 'clicked', 'dismissed', 'failed'
    error_message TEXT,
    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    delivered_at DATETIME,
    clicked_at DATETIME,
    FOREIGN KEY (notification_id) REFERENCES notification_queue(id),
    FOREIGN KEY (subscription_id) REFERENCES push_subscriptions(id)
);

-- User notification preferences
CREATE TABLE IF NOT EXISTS notification_preferences (
    user_id TEXT PRIMARY KEY,

    -- Global settings
    enabled BOOLEAN DEFAULT TRUE,
    quiet_hours_start TIME,               -- e.g., '22:00'
    quiet_hours_end TIME,                 -- e.g., '08:00'

    -- Category settings (JSON)
    category_settings TEXT,               -- {"task": {"enabled": true, "priority_threshold": 5}, ...}

    -- Flow protection
    respect_flow_state BOOLEAN DEFAULT TRUE,
    flow_interrupt_threshold INTEGER DEFAULT 8,

    -- Batching
    batch_notifications BOOLEAN DEFAULT TRUE,
    batch_window_minutes INTEGER DEFAULT 5,

    -- ADHD-specific
    max_notifications_per_hour INTEGER DEFAULT 6,
    cooldown_after_burst_minutes INTEGER DEFAULT 30,

    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Notification categories
CREATE TABLE IF NOT EXISTS notification_categories (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    default_priority INTEGER DEFAULT 5,
    default_icon TEXT,
    color TEXT,                           -- Hex color for UI
    can_batch BOOLEAN DEFAULT TRUE,
    can_suppress BOOLEAN DEFAULT TRUE,    -- Can be suppressed by flow state
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_queue_user_status ON notification_queue(user_id, status);
CREATE INDEX IF NOT EXISTS idx_queue_scheduled ON notification_queue(scheduled_for) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON push_subscriptions(user_id);
```

### Tool Specifications

#### 1. `tools/mobile/push/web_push.py`

```python
"""Web Push notification sender using VAPID."""

async def send_push(
    subscription_id: str,
    title: str,
    body: str,
    data: dict | None = None,
    icon_url: str | None = None,
    action_url: str | None = None,
    ttl: int = 86400
) -> dict:
    """
    Send a Web Push notification.

    Returns:
        {"success": True, "delivery_id": str} or
        {"success": False, "error": str, "should_unsubscribe": bool}
    """

async def send_batch(
    subscription_id: str,
    notifications: list[dict]
) -> dict:
    """
    Send a batched notification summarizing multiple items.

    Returns:
        {"success": True, "delivery_id": str, "count": int}
    """

def generate_vapid_keys() -> dict:
    """
    Generate new VAPID key pair for Web Push.

    Returns:
        {"public_key": str, "private_key": str}
    """

def get_vapid_public_key() -> str:
    """Get the server's VAPID public key for client subscription."""
```

#### 2. `tools/mobile/push/subscription_manager.py`

```python
"""Manage push notification subscriptions."""

async def register_subscription(
    user_id: str,
    endpoint: str,
    p256dh_key: str,
    auth_key: str,
    device_name: str | None = None,
    device_type: str = "web"
) -> dict:
    """
    Register a new push subscription.

    Returns:
        {"success": True, "subscription_id": str}
    """

async def unregister_subscription(subscription_id: str) -> dict:
    """Mark a subscription as inactive."""

async def get_user_subscriptions(user_id: str, active_only: bool = True) -> list[dict]:
    """Get all subscriptions for a user."""

async def prune_stale_subscriptions(days_inactive: int = 30) -> dict:
    """Remove subscriptions that haven't been used recently."""
```

#### 3. `tools/mobile/queue/notification_queue.py`

```python
"""Priority queue for notifications with batching support."""

async def enqueue(
    user_id: str,
    category: str,
    title: str,
    body: str | None = None,
    priority: int = 5,
    data: dict | None = None,
    scheduled_for: datetime | None = None,
    expires_at: datetime | None = None,
    batch_key: str | None = None,
    respect_flow_state: bool = True
) -> dict:
    """
    Add a notification to the queue.

    Returns:
        {"success": True, "notification_id": str, "status": "pending"|"scheduled"|"batched"}
    """

async def process_queue(limit: int = 100) -> dict:
    """
    Process pending notifications, respecting flow state and batching.

    Returns:
        {"processed": int, "sent": int, "batched": int, "suppressed": int}
    """

async def get_pending(user_id: str) -> list[dict]:
    """Get pending notifications for a user."""

async def cancel(notification_id: str) -> dict:
    """Cancel a pending notification."""
```

#### 4. `tools/mobile/queue/batcher.py`

```python
"""Batch related notifications to reduce interruptions."""

async def should_batch(notification: dict) -> bool:
    """Check if notification should be batched with others."""

async def get_batch(user_id: str, batch_key: str) -> list[dict]:
    """Get all notifications in a batch."""

async def create_batch_summary(notifications: list[dict]) -> dict:
    """
    Create a summary notification for a batch.

    Example: "3 task reminders" instead of 3 separate notifications.

    Returns:
        {"title": str, "body": str, "count": int, "notification_ids": list}
    """

async def process_expired_batches() -> dict:
    """Send batches that have exceeded their batch window."""
```

#### 5. `tools/mobile/queue/scheduler.py`

```python
"""Schedule notifications respecting user preferences and flow state."""

async def can_send_now(user_id: str, priority: int) -> dict:
    """
    Check if we can send a notification right now.

    Checks:
    - Quiet hours
    - Flow state (via flow_detector.py)
    - Rate limits
    - User preferences

    Returns:
        {"can_send": bool, "reason": str | None, "retry_at": datetime | None}
    """

async def get_next_send_window(user_id: str) -> datetime:
    """Get the next time we can send non-urgent notifications."""

async def is_in_quiet_hours(user_id: str) -> bool:
    """Check if user is currently in quiet hours."""

async def check_rate_limit(user_id: str) -> dict:
    """
    Check if user has exceeded notification rate limits.

    Returns:
        {"allowed": bool, "sent_this_hour": int, "limit": int, "reset_at": datetime}
    """
```

#### 6. `tools/mobile/preferences/user_preferences.py`

```python
"""Manage user notification preferences."""

async def get_preferences(user_id: str) -> dict:
    """Get user's notification preferences with defaults."""

async def update_preferences(user_id: str, **updates) -> dict:
    """Update user preferences."""

async def set_quiet_hours(user_id: str, start: str, end: str) -> dict:
    """Set quiet hours (e.g., '22:00' to '08:00')."""

async def set_category_preference(
    user_id: str,
    category: str,
    enabled: bool = True,
    priority_threshold: int = 1
) -> dict:
    """Configure preferences for a notification category."""

async def get_effective_settings(user_id: str, category: str) -> dict:
    """Get merged settings for a specific category."""
```

### Dashboard API Endpoints

Add to `tools/dashboard/backend/routes/`:

#### `push.py`

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/push/vapid-key | Get VAPID public key for subscription |
| POST | /api/push/subscribe | Register push subscription |
| DELETE | /api/push/subscribe/{id} | Unsubscribe device |
| GET | /api/push/subscriptions | List user's subscriptions |
| POST | /api/push/test | Send test notification |
| GET | /api/push/preferences | Get notification preferences |
| PUT | /api/push/preferences | Update preferences |
| GET | /api/push/categories | List notification categories |
| PUT | /api/push/categories/{id} | Update category preferences |
| GET | /api/push/history | Get notification history |
| GET | /api/push/stats | Get delivery statistics |

### Frontend (PWA) Changes

#### Service Worker (`public/sw.js`)

```javascript
// Handle push events
self.addEventListener('push', (event) => {
  const data = event.data?.json() ?? {};

  const options = {
    body: data.body,
    icon: data.icon || '/icons/dex-192.png',
    badge: '/icons/badge-72.png',
    data: data.data,
    actions: data.actions || [],
    tag: data.tag,  // Replaces existing notification with same tag
    renotify: data.renotify || false,
    requireInteraction: data.priority >= 8,
    silent: data.silent || false
  };

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

// Handle notification click
self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const actionUrl = event.notification.data?.action_url || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window' }).then((clientList) => {
      // Focus existing window or open new
      for (const client of clientList) {
        if (client.url === actionUrl && 'focus' in client) {
          return client.focus();
        }
      }
      return clients.openWindow(actionUrl);
    })
  );
});
```

#### Subscription Component

```typescript
// components/push/PushSubscription.tsx
interface PushSubscriptionProps {
  onSubscribed: (subscription: PushSubscription) => void;
  onError: (error: Error) => void;
}

// Handles:
// - Permission request with ADHD-friendly explanation
// - VAPID key fetch
// - Subscription creation
// - Backend registration
```

### Configuration

#### `args/mobile_push.yaml`

```yaml
# Mobile Push Notification Configuration

vapid:
  # Generate with: python -m tools.mobile.push.web_push generate-keys
  public_key: ""   # Set in .env: VAPID_PUBLIC_KEY
  private_key: ""  # Set in .env: VAPID_PRIVATE_KEY
  subject: "mailto:notifications@dexai.app"

defaults:
  # Rate limiting
  max_notifications_per_hour: 6
  cooldown_after_burst_minutes: 30

  # Batching
  batch_window_seconds: 300  # 5 minutes
  max_batch_size: 10

  # Flow protection
  respect_flow_state: true
  flow_interrupt_threshold: 8  # Priority 8+ can interrupt flow

  # Quiet hours (user can override)
  default_quiet_hours:
    start: "22:00"
    end: "08:00"
    timezone: "local"  # Use user's timezone

categories:
  task_reminder:
    default_priority: 6
    can_batch: true
    can_suppress: true
    icon: "task"
    color: "#4F46E5"

  commitment_due:
    default_priority: 8
    can_batch: false
    can_suppress: false  # Always deliver
    icon: "commitment"
    color: "#DC2626"

  message_received:
    default_priority: 5
    can_batch: true
    can_suppress: true
    icon: "message"
    color: "#059669"

  flow_state_ended:
    default_priority: 4
    can_batch: false
    can_suppress: false
    icon: "flow"
    color: "#8B5CF6"

  daily_summary:
    default_priority: 3
    can_batch: false
    can_suppress: true
    icon: "summary"
    color: "#6B7280"

# ADHD-specific settings
adhd:
  # Notification language
  use_supportive_language: true
  avoid_guilt_phrases: true

  # Timing
  transition_buffer_minutes: 5  # Don't notify right after task switch

  # Content
  max_title_length: 50
  max_body_length: 100
  include_single_action: true  # Always include one clear action
```

### Integration with Existing Systems

#### Connect to Smart Notifications (Phase 4)

```python
# In tools/automation/notify.py, add:

from tools.mobile.queue.notification_queue import enqueue as enqueue_push

async def send_notification(user_id: str, notification: Notification) -> dict:
    """Enhanced to include push notifications."""

    results = {"channels": []}

    # Existing channel delivery (Telegram, Discord, Slack)
    for channel in get_user_channels(user_id):
        result = await deliver_to_channel(channel, notification)
        results["channels"].append(result)

    # NEW: Also queue for push if user has subscriptions
    if await has_push_subscriptions(user_id):
        push_result = await enqueue_push(
            user_id=user_id,
            category=notification.category,
            title=notification.title,
            body=notification.body,
            priority=notification.priority,
            data={"notification_id": notification.id},
            respect_flow_state=notification.respect_flow_state
        )
        results["push"] = push_result

    return results
```

#### Connect to Flow Detector (Phase 4)

```python
# In tools/mobile/queue/scheduler.py

from tools.automation.flow_detector import get_flow_state

async def can_send_now(user_id: str, priority: int) -> dict:
    """Check flow state before sending."""

    flow_state = await get_flow_state(user_id)

    if flow_state.in_flow and priority < flow_state.interrupt_threshold:
        return {
            "can_send": False,
            "reason": "User in flow state",
            "retry_at": flow_state.expected_end
        }

    # ... other checks
```

### Implementation Order

1. **Create `tools/mobile/__init__.py`**
   - Path constants (PROJECT_ROOT, DB_PATH, CONFIG_PATH)
   - Database connection with table creation
   - Shared utilities

2. **Create `tools/mobile/models.py`**
   - `PushSubscription` dataclass
   - `Notification` dataclass
   - `NotificationCategory` dataclass
   - `DeliveryStatus` enum

3. **Create `tools/mobile/push/web_push.py`**
   - VAPID key generation and management
   - pywebpush integration
   - Send single notification
   - CLI for testing

4. **Create `tools/mobile/push/subscription_manager.py`**
   - Register/unregister subscriptions
   - List user subscriptions
   - Prune stale subscriptions

5. **Create `tools/mobile/preferences/user_preferences.py`**
   - Get/set preferences
   - Quiet hours management
   - Category preferences

6. **Create `tools/mobile/queue/scheduler.py`**
   - Quiet hours check
   - Flow state integration
   - Rate limiting

7. **Create `tools/mobile/queue/batcher.py`**
   - Batch detection
   - Batch summary creation
   - Expired batch processing

8. **Create `tools/mobile/queue/notification_queue.py`**
   - Enqueue notifications
   - Process queue (main loop)
   - Cancel/get pending

9. **Create `tools/mobile/push/delivery.py`**
   - Delivery with retry
   - Error handling (unsubscribe on 410)
   - Delivery logging

10. **Create `tools/dashboard/backend/routes/push.py`**
    - All API endpoints
    - Integration with main router

11. **Update Frontend**
    - Service worker for push handling
    - Subscription UI component
    - Preferences page
    - Notification history view

12. **Create `args/mobile_push.yaml`**
    - Default configuration
    - Category definitions

13. **Integration Testing**
    - End-to-end push flow
    - Batching behavior
    - Flow state respect

### Verification Checklist

#### Backend
- [ ] VAPID keys generated and stored securely
- [ ] Subscriptions stored in database
- [ ] Notifications queue correctly
- [ ] Batching groups related notifications
- [ ] Quiet hours respected
- [ ] Flow state checked before sending
- [ ] Rate limits enforced
- [ ] Failed subscriptions cleaned up
- [ ] Delivery logged for analytics

#### Frontend
- [ ] Service worker registered
- [ ] Push permission requested with explanation
- [ ] Subscription sent to backend
- [ ] Notifications display correctly
- [ ] Click opens correct URL
- [ ] Preferences UI functional
- [ ] Test notification works

#### ADHD-Specific
- [ ] No guilt language in notifications
- [ ] Single action per notification
- [ ] Batch summaries clear and concise
- [ ] Flow interruption only for high priority
- [ ] Quiet hours default enabled
- [ ] Rate limits prevent notification fatigue

---

## Phase 10b: Expo Mobile Wrapper (iOS)

**Status:** ✅ Complete

### Objective

Wrap the PWA in an Expo app to enable iOS push notifications and provide a native app experience.

### Directory Structure (Implemented)

```
mobile/
├── app.json                    # Expo configuration
├── App.tsx                     # Entry point (push init, WebView, deep linking)
├── package.json                # Dependencies
├── tsconfig.json               # TypeScript configuration
├── babel.config.js             # Babel config for Expo
├── src/
│   ├── components/
│   │   └── WebViewContainer.tsx  # WebView with auth injection, bridge, refresh
│   ├── services/
│   │   ├── push.ts               # Expo push token handling, listeners
│   │   └── background.ts         # Background fetch, silent push, badges
│   ├── utils/
│   │   ├── bridge.ts             # JS bridge for native <-> web communication
│   │   └── config.ts             # App configuration, feature flags
│   └── types/
│       └── index.ts              # TypeScript types
└── assets/
    ├── icon.png                  # Placeholder (replace for production)
    ├── splash.png                # Placeholder
    ├── adaptive-icon.png         # Placeholder
    ├── notification-icon.png     # Placeholder
    └── README.md                 # Asset requirements
```

### Key Features Implemented

| Component | Description |
|-----------|-------------|
| Expo Push Tokens | Register and manage Expo/FCM/APNs tokens |
| WebView Bridge | Bidirectional communication (native <-> web) |
| Background Fetch | Sync notifications, badge updates when backgrounded |
| App Badges | Badge count management via Expo APIs |
| Deep Linking | Handle dexai:// scheme for navigation |
| Error Handling | Graceful offline and error states |
| Pull-to-Refresh | Native refresh gesture support |

### Backend Additions

New file: `tools/mobile/push/native_tokens.py`
- `register_native_token()` - Store Expo/FCM/APNs tokens
- `unregister_native_token()` - Deactivate tokens on logout
- `get_native_tokens()` - List user's mobile tokens
- `send_native_push()` - Send via Expo Push Service
- `send_native_push_batch()` - Send to all user's devices

### New API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/push/native-token` | Register native push token |
| `DELETE /api/push/native-token/{token}` | Unregister token |
| `GET /api/push/native-tokens` | List native tokens |
| `POST /api/push/native-test` | Test native push |
| `GET /api/push/sync` | Background sync status |

### Database Changes (Migration-Safe)

```sql
-- Added to push_subscriptions table
ALTER TABLE push_subscriptions ADD COLUMN expo_token TEXT;
ALTER TABLE push_subscriptions ADD COLUMN fcm_token TEXT;
ALTER TABLE push_subscriptions ADD COLUMN apns_token TEXT;
ALTER TABLE push_subscriptions ADD COLUMN device_info TEXT;
```

### WebView Bridge Protocol

**Native -> Web Commands:**
- `AUTH_TOKEN` - Inject auth credentials
- `NAVIGATE` - Navigate to path
- `NOTIFICATION_RECEIVED` - Notify of new notification
- `BADGE_UPDATE` - Update badge display
- `DEVICE_INFO` - Send device information
- `THEME_CHANGE` - Notify of theme change

**Web -> Native Commands:**
- `READY` - WebView is ready
- `GET_AUTH` - Request auth token
- `NAVIGATE_NATIVE` - Open external URL
- `LOG` - Console logging

### ADHD-Friendly Features

1. **Permission Request** - Clear explanation of notification value
2. **Gentle Vibration** - Short patterns to avoid startle
3. **High-Priority Channel** - Urgent items break through
4. **Badge Management** - Clear on app open
5. **Silent Sync** - Background updates without interruption

### Build Instructions

```bash
cd mobile

# Install dependencies
npm install

# Start development server
npm start

# Build for iOS (requires EAS CLI)
npm run build:ios

# Build for Android
npm run build:android
```

### Environment Variables

For production, set in `app.json` extras or `.env`:
- `EXPO_PUBLIC_API_URL` - Backend API endpoint
- `EXPO_PUBLIC_DASHBOARD_URL` - PWA dashboard URL
- `EXPO_PUBLIC_DEBUG` - Enable debug logging

### Verification Checklist

- [x] Expo project structure created
- [x] Push notification service implemented
- [x] Background fetch task registered
- [x] WebView bridge functional
- [x] Deep linking configured
- [x] Backend native token endpoints added
- [x] Database schema updated
- [x] Documentation updated

---

## Phase 10c: Native Enhancements

### Objective

Add native features that can't be achieved with PWA alone.

### Features

| Feature | Description | Platform |
|---------|-------------|----------|
| **Background Sync** | Sync tasks/notifications in background | iOS, Android |
| **Widgets** | Home screen widget showing next task | iOS 14+, Android |
| **Watch App** | Quick task view on Apple Watch | watchOS |
| **Siri Shortcuts** | "Hey Siri, what's my next task?" | iOS |
| **Quick Actions** | 3D Touch shortcuts | iOS |

### Implementation

This phase will be scoped in detail after 10a and 10b are validated with users.

---

## ADHD-Specific Design Principles

### Notification Content

| Principle | Implementation |
|-----------|----------------|
| **No guilt** | Never say "You missed..." or "Overdue" |
| **Forward-facing** | "Ready when you are" not "You haven't done this" |
| **Single action** | Each notification has ONE clear action |
| **Supportive tone** | "Your next step" not "You need to" |

### Notification Timing

| Principle | Implementation |
|-----------|----------------|
| **Flow protection** | Don't interrupt hyperfocus for low-priority items |
| **Transition buffer** | Wait 5 min after task switch before notifying |
| **Batching** | Group related items to reduce interruption count |
| **Rate limiting** | Max 6/hour, cooldown after bursts |

### User Control

| Principle | Implementation |
|-----------|----------------|
| **Granular control** | Per-category enable/disable |
| **Quiet hours** | Automatic DND with easy override |
| **Emergency bypass** | High-priority always gets through |
| **Easy unsubscribe** | One-tap disable from any notification |

---

## Dependencies

### Python Packages

```
pywebpush>=1.14.0    # Web Push protocol
cryptography>=41.0   # VAPID key handling
```

### Frontend Packages

```
# Already in dashboard, no new deps for 10a
# For 10b:
expo
expo-notifications
expo-device
react-native-webview
```

---

## Security Considerations

- VAPID private key stored in vault (encrypted)
- Push endpoints validated before storage
- Subscription tokens never logged
- Rate limiting prevents abuse
- Unsubscribe on any 410 response
- No sensitive data in notification payload (use IDs, fetch on click)

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Subscription rate | >50% of active users |
| Delivery success rate | >95% |
| Click-through rate | >20% |
| Unsubscribe rate | <5% per month |
| Flow interruptions | <5% of notifications during flow |
| User-reported notification fatigue | <10% |

---

*This guide will be updated as implementation progresses.*
