/**
 * DexAI Mobile - TypeScript Type Definitions
 *
 * Shared types for the Expo mobile wrapper application.
 */

// =============================================================================
// Push Notification Types
// =============================================================================

/**
 * Native push token information for Expo/FCM/APNs
 */
export interface PushToken {
  /** The push token string */
  token: string;
  /** Token type: 'expo', 'fcm', or 'apns' */
  type: 'expo' | 'fcm' | 'apns';
  /** When the token was obtained */
  obtainedAt: Date;
  /** Device identifier for this token */
  deviceId?: string;
}

/**
 * Push notification data payload from server
 */
export interface NotificationData {
  /** Unique notification identifier */
  id: string;
  /** Notification category for filtering/display */
  category: NotificationCategory;
  /** Priority level (1-10, 10 = highest) */
  priority: number;
  /** URL to navigate to on tap */
  actionUrl?: string;
  /** Additional data payload */
  data?: Record<string, unknown>;
  /** Tag for notification replacement */
  tag?: string;
  /** Whether notification requires interaction */
  requireInteraction?: boolean;
  /** Silent notification flag */
  silent?: boolean;
}

/**
 * Notification categories matching backend
 */
export type NotificationCategory =
  | 'task_reminder'
  | 'commitment_due'
  | 'message_received'
  | 'flow_state_ended'
  | 'daily_summary'
  | 'system'
  | 'test';

/**
 * Full notification object for display
 */
export interface Notification {
  /** Notification title */
  title: string;
  /** Notification body text */
  body: string;
  /** Structured data payload */
  data: NotificationData;
  /** Icon URL or local asset */
  icon?: string;
  /** Badge count to set */
  badge?: number;
}

// =============================================================================
// WebView Bridge Types
// =============================================================================

/**
 * Commands that can be sent from native to WebView
 */
export type BridgeCommandToWeb =
  | 'AUTH_TOKEN'
  | 'NAVIGATE'
  | 'NOTIFICATION_RECEIVED'
  | 'BADGE_UPDATE'
  | 'DEVICE_INFO'
  | 'THEME_CHANGE';

/**
 * Commands that can be received from WebView
 */
export type BridgeCommandFromWeb =
  | 'READY'
  | 'GET_AUTH'
  | 'GET_DEVICE_INFO'
  | 'SHOW_NOTIFICATION'
  | 'UPDATE_BADGE'
  | 'NAVIGATE_NATIVE'
  | 'LOG';

/**
 * Message structure for WebView bridge communication
 */
export interface BridgeMessage<T = unknown> {
  /** Command identifier */
  command: BridgeCommandToWeb | BridgeCommandFromWeb;
  /** Message payload */
  payload: T;
  /** Unique message ID for request/response matching */
  messageId?: string;
  /** Timestamp of message creation */
  timestamp: number;
}

/**
 * Auth token message payload
 */
export interface AuthTokenPayload {
  /** JWT access token */
  accessToken: string;
  /** Token expiration timestamp */
  expiresAt: number;
  /** User identifier */
  userId: string;
}

/**
 * Navigation message payload
 */
export interface NavigationPayload {
  /** Path to navigate to */
  path: string;
  /** Query parameters */
  params?: Record<string, string>;
  /** Replace current history entry */
  replace?: boolean;
}

/**
 * Device info payload
 */
export interface DeviceInfoPayload {
  /** Device platform */
  platform: 'ios' | 'android';
  /** OS version */
  osVersion: string;
  /** Device model */
  model: string;
  /** App version */
  appVersion: string;
  /** Is device a tablet */
  isTablet: boolean;
  /** Device unique identifier */
  deviceId: string;
  /** Push notification permission status */
  pushPermission: 'granted' | 'denied' | 'undetermined';
}

// =============================================================================
// Background Task Types
// =============================================================================

/**
 * Background fetch result status
 */
export type BackgroundFetchResult =
  | 'newData'
  | 'noData'
  | 'failed';

/**
 * Background task status
 */
export interface BackgroundTaskStatus {
  /** Task identifier */
  taskName: string;
  /** Whether task is registered */
  isRegistered: boolean;
  /** Last execution time */
  lastExecutedAt?: Date;
  /** Last result */
  lastResult?: BackgroundFetchResult;
  /** Error message if failed */
  errorMessage?: string;
}

// =============================================================================
// App State Types
// =============================================================================

/**
 * App-wide state
 */
export interface AppState {
  /** Whether app is initialized */
  initialized: boolean;
  /** Current push token */
  pushToken: PushToken | null;
  /** WebView is ready */
  webViewReady: boolean;
  /** Current user ID */
  userId: string | null;
  /** Is authenticated */
  isAuthenticated: boolean;
  /** Current badge count */
  badgeCount: number;
  /** Network connectivity status */
  isOnline: boolean;
  /** App is in foreground */
  isActive: boolean;
}

/**
 * Configuration for the mobile app
 */
export interface AppConfig {
  /** Backend API URL */
  apiUrl: string;
  /** Dashboard web URL */
  dashboardUrl: string;
  /** Enable debug logging */
  debug: boolean;
  /** Background fetch minimum interval in seconds */
  backgroundFetchInterval: number;
  /** Maximum badge count to display */
  maxBadgeCount: number;
}

// =============================================================================
// Error Types
// =============================================================================

/**
 * Structured error for app operations
 */
export interface AppError {
  /** Error code */
  code: string;
  /** Human-readable message */
  message: string;
  /** Additional context */
  details?: Record<string, unknown>;
  /** Whether error is recoverable */
  recoverable: boolean;
}

/**
 * Push registration error codes
 */
export type PushErrorCode =
  | 'PERMISSION_DENIED'
  | 'REGISTRATION_FAILED'
  | 'TOKEN_UPLOAD_FAILED'
  | 'DEVICE_NOT_SUPPORTED'
  | 'NETWORK_ERROR';

// =============================================================================
// API Response Types
// =============================================================================

/**
 * Generic API response wrapper
 */
export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}

/**
 * Native token registration request
 */
export interface NativeTokenRegistrationRequest {
  token: string;
  tokenType: 'expo' | 'fcm' | 'apns';
  deviceInfo: Partial<DeviceInfoPayload>;
}

/**
 * Native token registration response
 */
export interface NativeTokenRegistrationResponse {
  success: boolean;
  subscriptionId: string;
  reactivated?: boolean;
}
