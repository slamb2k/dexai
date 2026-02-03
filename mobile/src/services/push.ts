/**
 * DexAI Mobile - Push Notification Service
 *
 * Handles Expo push notification registration, token management,
 * and notification event handling for iOS and Android.
 *
 * Key responsibilities:
 * - Request notification permissions
 * - Obtain Expo push tokens (or FCM/APNs for bare workflow)
 * - Send tokens to DexAI backend
 * - Handle foreground/background notification events
 * - Manage notification response actions
 */

import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import Constants from 'expo-constants';
import { Platform, Alert } from 'react-native';
import {
  PushToken,
  NotificationData,
  NativeTokenRegistrationRequest,
  NativeTokenRegistrationResponse,
  AppError,
  PushErrorCode,
} from '../types';
import { config, debugLog, debugError, buildApiUrl } from '../utils/config';
import { notifyNotificationReceived, updateBadge } from '../utils/bridge';

// =============================================================================
// Configuration
// =============================================================================

/**
 * Configure notification behavior for foreground notifications
 */
Notifications.setNotificationHandler({
  handleNotification: async (notification) => {
    const data = notification.request.content.data as NotificationData;
    const priority = data?.priority ?? 5;

    // High priority notifications always show
    // Lower priority can be suppressed if user preference says so
    const shouldShow = priority >= 7;

    debugLog('Notification handler:', {
      title: notification.request.content.title,
      priority,
      shouldShow,
    });

    return {
      shouldShowAlert: shouldShow,
      shouldPlaySound: priority >= 8,
      shouldSetBadge: true,
    };
  },
});

// =============================================================================
// State
// =============================================================================

let pushToken: PushToken | null = null;
let notificationListener: Notifications.Subscription | null = null;
let responseListener: Notifications.Subscription | null = null;
let userId: string | null = null;

// =============================================================================
// Permission & Registration
// =============================================================================

/**
 * Check if device supports push notifications
 */
export const isDeviceSupported = (): boolean => {
  return Device.isDevice;
};

/**
 * Get current notification permission status
 */
export const getPermissionStatus = async (): Promise<
  'granted' | 'denied' | 'undetermined'
> => {
  const { status } = await Notifications.getPermissionsAsync();

  if (status === 'granted') return 'granted';
  if (status === 'denied') return 'denied';
  return 'undetermined';
};

/**
 * Request notification permissions with ADHD-friendly explanation
 */
export const requestPermissions = async (): Promise<boolean> => {
  if (!isDeviceSupported()) {
    debugError('Push: Device does not support push notifications (simulator?)');
    return false;
  }

  const { status: existingStatus } = await Notifications.getPermissionsAsync();

  if (existingStatus === 'granted') {
    debugLog('Push: Permissions already granted');
    return true;
  }

  // Show explanation before requesting (ADHD-friendly - explain the value)
  return new Promise((resolve) => {
    Alert.alert(
      'Stay on Track',
      'DexAI can send gentle reminders to help you stay focused on what matters. ' +
        'We limit notifications to avoid overwhelm and respect your focus time.',
      [
        {
          text: 'Not Now',
          style: 'cancel',
          onPress: () => resolve(false),
        },
        {
          text: 'Enable',
          onPress: async () => {
            const { status } = await Notifications.requestPermissionsAsync();
            resolve(status === 'granted');
          },
        },
      ]
    );
  });
};

/**
 * Register for push notifications and get token
 *
 * This is the main entry point for push setup.
 * Call this after app initialization and user authentication.
 */
export const registerForPushNotificationsAsync = async (
  currentUserId: string
): Promise<PushToken | null> => {
  userId = currentUserId;

  if (!isDeviceSupported()) {
    const error: AppError = {
      code: 'DEVICE_NOT_SUPPORTED',
      message: 'Push notifications are not supported on this device',
      recoverable: false,
    };
    debugError('Push:', error);
    return null;
  }

  const hasPermission = await requestPermissions();
  if (!hasPermission) {
    debugLog('Push: User declined notifications');
    return null;
  }

  try {
    // Get Expo push token (handles FCM/APNs under the hood)
    const expoPushToken = await Notifications.getExpoPushTokenAsync({
      projectId: Constants.expoConfig?.extra?.eas?.projectId,
    });

    const token: PushToken = {
      token: expoPushToken.data,
      type: 'expo',
      obtainedAt: new Date(),
      deviceId: Constants.installationId,
    };

    debugLog('Push: Got token', token.token.substring(0, 20) + '...');

    // Configure Android channel
    if (Platform.OS === 'android') {
      await setupAndroidChannel();
    }

    // Send to backend
    const sent = await sendTokenToServer(token);
    if (!sent) {
      debugError('Push: Failed to send token to server');
      // Still return token - we can retry later
    }

    pushToken = token;
    return token;
  } catch (error) {
    debugError('Push: Registration failed', error);
    return null;
  }
};

/**
 * Setup Android notification channel with ADHD-friendly defaults
 */
const setupAndroidChannel = async (): Promise<void> => {
  await Notifications.setNotificationChannelAsync('default', {
    name: 'DexAI Notifications',
    importance: Notifications.AndroidImportance.DEFAULT,
    vibrationPattern: [0, 250], // Short, gentle vibration
    lightColor: '#4F46E5',
    sound: 'default',
    enableLights: true,
    enableVibrate: true,
    showBadge: true,
  });

  // Create a high-priority channel for urgent items
  await Notifications.setNotificationChannelAsync('urgent', {
    name: 'Urgent Notifications',
    importance: Notifications.AndroidImportance.HIGH,
    vibrationPattern: [0, 500, 200, 500],
    lightColor: '#DC2626',
    sound: 'default',
    enableLights: true,
    enableVibrate: true,
    showBadge: true,
  });

  debugLog('Push: Android channels configured');
};

// =============================================================================
// Token Server Communication
// =============================================================================

/**
 * Send push token to DexAI backend
 */
export const sendTokenToServer = async (token: PushToken): Promise<boolean> => {
  if (!userId) {
    debugError('Push: Cannot send token - no user ID');
    return false;
  }

  const request: NativeTokenRegistrationRequest = {
    token: token.token,
    tokenType: token.type,
    deviceInfo: {
      platform: Platform.OS as 'ios' | 'android',
      osVersion: Platform.Version?.toString() ?? 'unknown',
      model: Device.modelName ?? 'unknown',
      appVersion: Constants.expoConfig?.version ?? '1.0.0',
      isTablet: Device.deviceType === Device.DeviceType.TABLET,
      deviceId: Constants.installationId ?? 'unknown',
      pushPermission: 'granted',
    },
  };

  try {
    const response = await fetch(
      buildApiUrl(`/api/push/native-token?user_id=${userId}`),
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(request),
      }
    );

    if (!response.ok) {
      const errorText = await response.text();
      debugError('Push: Server rejected token', errorText);
      return false;
    }

    const result: NativeTokenRegistrationResponse = await response.json();
    debugLog('Push: Token registered', result);
    return result.success;
  } catch (error) {
    debugError('Push: Network error sending token', error);
    return false;
  }
};

/**
 * Unregister token from server (e.g., on logout)
 */
export const unregisterToken = async (): Promise<boolean> => {
  if (!pushToken || !userId) {
    return true; // Nothing to unregister
  }

  try {
    const response = await fetch(
      buildApiUrl(`/api/push/native-token/${pushToken.token}?user_id=${userId}`),
      {
        method: 'DELETE',
      }
    );

    if (!response.ok) {
      debugError('Push: Failed to unregister token');
      return false;
    }

    pushToken = null;
    return true;
  } catch (error) {
    debugError('Push: Network error unregistering token', error);
    return false;
  }
};

// =============================================================================
// Notification Event Handlers
// =============================================================================

/**
 * Handle notification received while app is in foreground
 */
export const handleNotificationReceived = (
  notification: Notifications.Notification
): void => {
  const data = notification.request.content.data as NotificationData;

  debugLog('Push: Notification received in foreground', {
    id: data?.id,
    title: notification.request.content.title,
    category: data?.category,
  });

  // Forward to WebView so dashboard can update
  if (data) {
    notifyNotificationReceived(data);
  }
};

/**
 * Handle user interaction with notification (tap, action button)
 */
export const handleNotificationResponse = (
  response: Notifications.NotificationResponse
): void => {
  const notification = response.notification;
  const data = notification.request.content.data as NotificationData;
  const actionId = response.actionIdentifier;

  debugLog('Push: Notification response', {
    id: data?.id,
    action: actionId,
    url: data?.actionUrl,
  });

  // Handle default tap action
  if (actionId === Notifications.DEFAULT_ACTION_IDENTIFIER && data?.actionUrl) {
    // Navigate in WebView to the action URL
    // This will be handled by the App component's navigation logic
    // We emit an event that App.tsx listens to
  }

  // Track click with backend
  trackNotificationAction(data?.id, 'clicked');
};

/**
 * Track notification action with backend
 */
const trackNotificationAction = async (
  notificationId: string | undefined,
  action: 'clicked' | 'dismissed'
): Promise<void> => {
  if (!notificationId) return;

  try {
    await fetch(buildApiUrl(`/api/push/track/${action}?notification_id=${notificationId}`), {
      method: 'POST',
    });
  } catch (error) {
    debugError('Push: Failed to track action', error);
  }
};

// =============================================================================
// Listener Setup
// =============================================================================

/**
 * Set up notification event listeners
 *
 * Call this once during app initialization.
 * Returns cleanup function to remove listeners.
 */
export const setupNotificationListeners = (): (() => void) => {
  // Listener for notifications received while app is foregrounded
  notificationListener = Notifications.addNotificationReceivedListener(
    handleNotificationReceived
  );

  // Listener for user interactions with notifications
  responseListener = Notifications.addNotificationResponseReceivedListener(
    handleNotificationResponse
  );

  debugLog('Push: Listeners set up');

  // Return cleanup function
  return () => {
    if (notificationListener) {
      Notifications.removeNotificationSubscription(notificationListener);
      notificationListener = null;
    }
    if (responseListener) {
      Notifications.removeNotificationSubscription(responseListener);
      responseListener = null;
    }
    debugLog('Push: Listeners removed');
  };
};

// =============================================================================
// Badge Management
// =============================================================================

/**
 * Set app icon badge count
 */
export const setBadgeCount = async (count: number): Promise<void> => {
  const clampedCount = Math.min(count, config.maxBadgeCount);

  await Notifications.setBadgeCountAsync(clampedCount);
  updateBadge(clampedCount);

  debugLog('Push: Badge set to', clampedCount);
};

/**
 * Clear app icon badge
 */
export const clearBadge = async (): Promise<void> => {
  await Notifications.setBadgeCountAsync(0);
  updateBadge(0);

  debugLog('Push: Badge cleared');
};

/**
 * Get current badge count
 */
export const getBadgeCount = async (): Promise<number> => {
  return await Notifications.getBadgeCountAsync();
};

// =============================================================================
// Utility Functions
// =============================================================================

/**
 * Get the current push token
 */
export const getCurrentToken = (): PushToken | null => {
  return pushToken;
};

/**
 * Check if push notifications are enabled
 */
export const isPushEnabled = async (): Promise<boolean> => {
  const status = await getPermissionStatus();
  return status === 'granted' && pushToken !== null;
};

/**
 * Schedule a local notification (for testing or offline reminders)
 */
export const scheduleLocalNotification = async (
  title: string,
  body: string,
  data?: NotificationData,
  trigger?: Notifications.NotificationTriggerInput
): Promise<string> => {
  const id = await Notifications.scheduleNotificationAsync({
    content: {
      title,
      body,
      data,
      sound: true,
    },
    trigger: trigger ?? null, // null = immediate
  });

  debugLog('Push: Scheduled local notification', id);
  return id;
};

/**
 * Cancel a scheduled notification
 */
export const cancelScheduledNotification = async (id: string): Promise<void> => {
  await Notifications.cancelScheduledNotificationAsync(id);
  debugLog('Push: Cancelled notification', id);
};

/**
 * Cancel all scheduled notifications
 */
export const cancelAllScheduledNotifications = async (): Promise<void> => {
  await Notifications.cancelAllScheduledNotificationsAsync();
  debugLog('Push: Cancelled all notifications');
};

// =============================================================================
// Exports
// =============================================================================

export default {
  registerForPushNotificationsAsync,
  sendTokenToServer,
  unregisterToken,
  setupNotificationListeners,
  setBadgeCount,
  clearBadge,
  getBadgeCount,
  getCurrentToken,
  isPushEnabled,
  isDeviceSupported,
  getPermissionStatus,
  requestPermissions,
  scheduleLocalNotification,
  cancelScheduledNotification,
  cancelAllScheduledNotifications,
};
