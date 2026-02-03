/**
 * DexAI Mobile - Background Fetch Service
 *
 * Handles background tasks for syncing notifications and data
 * when the app is not in the foreground.
 *
 * Key responsibilities:
 * - Register background fetch task
 * - Sync pending notifications
 * - Handle silent push notifications
 * - Manage badge count updates
 */

import * as BackgroundFetch from 'expo-background-fetch';
import * as TaskManager from 'expo-task-manager';
import * as Notifications from 'expo-notifications';
import { config, debugLog, debugError, buildApiUrl } from '../utils/config';
import { BackgroundFetchResult, BackgroundTaskStatus } from '../types';
import { setBadgeCount } from './push';

// =============================================================================
// Constants
// =============================================================================

const BACKGROUND_FETCH_TASK = 'dexai-background-fetch';
const BACKGROUND_NOTIFICATION_TASK = 'dexai-background-notification';

// =============================================================================
// Background Fetch Task Definition
// =============================================================================

/**
 * Define the background fetch task
 *
 * This task runs periodically when the app is backgrounded.
 * iOS minimum interval is ~15 minutes, Android can be more frequent.
 */
TaskManager.defineTask(BACKGROUND_FETCH_TASK, async () => {
  const now = Date.now();
  debugLog(`Background fetch: Started at ${new Date(now).toISOString()}`);

  try {
    // Sync pending data with server
    const result = await syncWithServer();

    if (result.hasNewData) {
      debugLog('Background fetch: New data received', result);
      return BackgroundFetch.BackgroundFetchResult.NewData;
    }

    debugLog('Background fetch: No new data');
    return BackgroundFetch.BackgroundFetchResult.NoData;
  } catch (error) {
    debugError('Background fetch: Failed', error);
    return BackgroundFetch.BackgroundFetchResult.Failed;
  }
});

/**
 * Define the background notification task
 *
 * This task handles silent/background push notifications.
 */
TaskManager.defineTask(
  BACKGROUND_NOTIFICATION_TASK,
  async ({ data, error, executionInfo }) => {
    if (error) {
      debugError('Background notification: Error', error);
      return;
    }

    debugLog('Background notification: Received', data);

    try {
      // Handle the silent push data
      await handleSilentPush(data as Record<string, unknown>);
    } catch (err) {
      debugError('Background notification: Handler failed', err);
    }
  }
);

// =============================================================================
// Registration Functions
// =============================================================================

/**
 * Register background fetch task
 *
 * Call this during app initialization.
 */
export const registerBackgroundFetch = async (): Promise<boolean> => {
  try {
    // Check if task is already registered
    const isRegistered = await TaskManager.isTaskRegisteredAsync(
      BACKGROUND_FETCH_TASK
    );

    if (isRegistered) {
      debugLog('Background fetch: Already registered');
      return true;
    }

    // Register the task
    await BackgroundFetch.registerTaskAsync(BACKGROUND_FETCH_TASK, {
      minimumInterval: config.backgroundFetchInterval,
      stopOnTerminate: false, // Android: continue running after app killed
      startOnBoot: true, // Android: start after device reboot
    });

    debugLog('Background fetch: Registered successfully');
    return true;
  } catch (error) {
    debugError('Background fetch: Registration failed', error);
    return false;
  }
};

/**
 * Unregister background fetch task
 */
export const unregisterBackgroundFetch = async (): Promise<boolean> => {
  try {
    const isRegistered = await TaskManager.isTaskRegisteredAsync(
      BACKGROUND_FETCH_TASK
    );

    if (!isRegistered) {
      return true;
    }

    await BackgroundFetch.unregisterTaskAsync(BACKGROUND_FETCH_TASK);
    debugLog('Background fetch: Unregistered');
    return true;
  } catch (error) {
    debugError('Background fetch: Unregister failed', error);
    return false;
  }
};

/**
 * Register background notification handler
 */
export const registerBackgroundNotifications = async (): Promise<boolean> => {
  try {
    // Set the handler for background notifications
    Notifications.registerTaskAsync(BACKGROUND_NOTIFICATION_TASK);
    debugLog('Background notifications: Registered');
    return true;
  } catch (error) {
    debugError('Background notifications: Registration failed', error);
    return false;
  }
};

// =============================================================================
// Sync Functions
// =============================================================================

interface SyncResult {
  hasNewData: boolean;
  badgeCount: number;
  pendingNotifications: number;
  error?: string;
}

/**
 * Sync with server during background fetch
 */
const syncWithServer = async (): Promise<SyncResult> => {
  const result: SyncResult = {
    hasNewData: false,
    badgeCount: 0,
    pendingNotifications: 0,
  };

  try {
    // Fetch current status from server
    const response = await fetch(buildApiUrl('/api/push/sync'), {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      result.error = `Server returned ${response.status}`;
      return result;
    }

    const data = await response.json();

    // Update badge count if changed
    if (data.badgeCount !== undefined) {
      const currentBadge = await Notifications.getBadgeCountAsync();
      if (currentBadge !== data.badgeCount) {
        await setBadgeCount(data.badgeCount);
        result.hasNewData = true;
      }
      result.badgeCount = data.badgeCount;
    }

    // Check for pending notifications
    if (data.pendingNotifications?.length > 0) {
      result.pendingNotifications = data.pendingNotifications.length;
      result.hasNewData = true;

      // Display any pending notifications
      for (const notification of data.pendingNotifications) {
        await showPendingNotification(notification);
      }
    }

    return result;
  } catch (error) {
    result.error = error instanceof Error ? error.message : 'Unknown error';
    return result;
  }
};

/**
 * Show a pending notification from background sync
 */
const showPendingNotification = async (notification: {
  id: string;
  title: string;
  body: string;
  data?: Record<string, unknown>;
  priority?: number;
}): Promise<void> => {
  await Notifications.scheduleNotificationAsync({
    content: {
      title: notification.title,
      body: notification.body,
      data: notification.data,
      sound: notification.priority && notification.priority >= 8,
    },
    trigger: null, // Immediate
  });
};

/**
 * Handle silent push notification
 *
 * Silent pushes can update badge, trigger sync, etc. without showing a notification.
 */
const handleSilentPush = async (
  data: Record<string, unknown>
): Promise<void> => {
  debugLog('Silent push data:', data);

  // Handle badge update
  if (typeof data.badge === 'number') {
    await setBadgeCount(data.badge);
  }

  // Handle sync trigger
  if (data.sync === true) {
    await syncWithServer();
  }

  // Handle specific actions
  if (data.action === 'clear_badge') {
    await setBadgeCount(0);
  }

  if (data.action === 'refresh_token') {
    // Token refresh requested - handled by push service
    debugLog('Silent push: Token refresh requested');
  }
};

// =============================================================================
// Status Functions
// =============================================================================

/**
 * Get background fetch task status
 */
export const getBackgroundFetchStatus = async (): Promise<BackgroundTaskStatus> => {
  const isRegistered = await TaskManager.isTaskRegisteredAsync(
    BACKGROUND_FETCH_TASK
  );

  const status = await BackgroundFetch.getStatusAsync();

  return {
    taskName: BACKGROUND_FETCH_TASK,
    isRegistered,
    lastExecutedAt: undefined, // Would need to track this separately
    lastResult: undefined,
  };
};

/**
 * Check if background fetch is available on this device
 */
export const isBackgroundFetchAvailable = async (): Promise<boolean> => {
  const status = await BackgroundFetch.getStatusAsync();
  return status === BackgroundFetch.BackgroundFetchStatus.Available;
};

/**
 * Get background fetch availability status as string
 */
export const getBackgroundFetchAvailability = async (): Promise<string> => {
  const status = await BackgroundFetch.getStatusAsync();

  switch (status) {
    case BackgroundFetch.BackgroundFetchStatus.Available:
      return 'available';
    case BackgroundFetch.BackgroundFetchStatus.Denied:
      return 'denied';
    case BackgroundFetch.BackgroundFetchStatus.Restricted:
      return 'restricted';
    default:
      return 'unknown';
  }
};

// =============================================================================
// Badge Management (Background)
// =============================================================================

/**
 * Increment badge count from background
 */
export const incrementBadge = async (amount = 1): Promise<number> => {
  const current = await Notifications.getBadgeCountAsync();
  const newCount = Math.min(current + amount, config.maxBadgeCount);
  await setBadgeCount(newCount);
  return newCount;
};

/**
 * Decrement badge count from background
 */
export const decrementBadge = async (amount = 1): Promise<number> => {
  const current = await Notifications.getBadgeCountAsync();
  const newCount = Math.max(current - amount, 0);
  await setBadgeCount(newCount);
  return newCount;
};

// =============================================================================
// Cleanup
// =============================================================================

/**
 * Clean up all background tasks
 *
 * Call this when user logs out or app is being reset.
 */
export const cleanupBackgroundTasks = async (): Promise<void> => {
  await unregisterBackgroundFetch();

  try {
    await TaskManager.unregisterTaskAsync(BACKGROUND_NOTIFICATION_TASK);
  } catch {
    // Task might not be registered
  }

  await setBadgeCount(0);
  debugLog('Background tasks: Cleaned up');
};

// =============================================================================
// Exports
// =============================================================================

export default {
  registerBackgroundFetch,
  unregisterBackgroundFetch,
  registerBackgroundNotifications,
  getBackgroundFetchStatus,
  isBackgroundFetchAvailable,
  getBackgroundFetchAvailability,
  incrementBadge,
  decrementBadge,
  cleanupBackgroundTasks,
  BACKGROUND_FETCH_TASK,
  BACKGROUND_NOTIFICATION_TASK,
};
