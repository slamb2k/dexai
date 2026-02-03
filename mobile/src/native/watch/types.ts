/**
 * DexAI Mobile - Watch Types
 *
 * TypeScript types for Apple Watch communication.
 */

// =============================================================================
// Watch Message Types
// =============================================================================

/**
 * Message types that can be sent to/from Watch
 */
export type WatchMessageType =
  | 'SYNC_STATE' // Sync current state
  | 'TASK_UPDATE' // Task was updated
  | 'QUICK_ACTION' // Quick action from watch
  | 'COMPLICATION_UPDATE' // Complication needs refresh
  | 'SETTINGS_CHANGED' // Settings were changed
  | 'HEARTBEAT'; // Keep-alive ping

/**
 * Base message structure for Watch communication
 */
export interface WatchMessage<T = unknown> {
  /** Message type identifier */
  type: WatchMessageType;
  /** Message payload */
  payload: T;
  /** Timestamp of message creation */
  timestamp: number;
  /** Optional message ID for request/response matching */
  messageId?: string;
}

// =============================================================================
// State Types
// =============================================================================

/**
 * Current task data for Watch display
 */
export interface WatchTaskData {
  /** Task ID */
  id: string;
  /** Task title (truncated for Watch) */
  title: string;
  /** Current step description */
  currentStep: string | null;
  /** Step progress (e.g., "2/5") */
  stepProgress: string | null;
  /** Priority level (1-10) */
  priority: number;
  /** Due time if set */
  dueTime: string | null;
  /** Is task overdue */
  isOverdue: boolean;
}

/**
 * Complete Watch app state
 */
export interface WatchAppState {
  /** Whether phone app is reachable */
  isPhoneReachable: boolean;
  /** Current task data */
  currentTask: WatchTaskData | null;
  /** Number of tasks for today */
  todayTaskCount: number;
  /** Current energy level */
  energyLevel: 'high' | 'medium' | 'low' | 'unknown';
  /** Is user in flow state */
  inFlowState: boolean;
  /** Last sync timestamp */
  lastSync: string | null;
  /** Any pending quick actions */
  pendingActions: number;
}

// =============================================================================
// Complication Types
// =============================================================================

/**
 * Complication data for Watch face
 */
export interface ComplicationData {
  /** Complication identifier */
  id: string;
  /** Complication type */
  type: ComplicationType;
  /** Display data based on type */
  data: ComplicationDisplayData;
  /** When this data expires */
  expiresAt: string;
}

/**
 * Types of complications supported
 */
export type ComplicationType =
  | 'current_task' // Show current task title
  | 'next_reminder' // Show next reminder time
  | 'task_count' // Show remaining task count
  | 'energy_level'; // Show current energy level

/**
 * Display data for complications
 */
export interface ComplicationDisplayData {
  /** Short text (for small complications) */
  shortText?: string;
  /** Long text (for larger complications) */
  longText?: string;
  /** Numeric value */
  value?: number;
  /** Gauge fill percentage (0-1) */
  gaugeValue?: number;
  /** Tint color */
  tintColor?: string;
  /** SF Symbol name (iOS) */
  symbolName?: string;
}

// =============================================================================
// Quick Action Types
// =============================================================================

/**
 * Quick actions available on Watch
 */
export type QuickActionType =
  | 'complete_step' // Mark current step as done
  | 'skip_task' // Skip current task
  | 'snooze_reminder' // Snooze active reminder
  | 'start_focus' // Start a focus session
  | 'end_focus' // End current focus session
  | 'check_in'; // Quick check-in

/**
 * Quick action request from Watch
 */
export interface QuickActionRequest {
  /** Action type */
  action: QuickActionType;
  /** Optional task ID */
  taskId?: string;
  /** Optional duration (for snooze, focus) */
  durationMinutes?: number;
}

/**
 * Quick action response to Watch
 */
export interface QuickActionResponse {
  /** Whether action succeeded */
  success: boolean;
  /** Updated state after action */
  newState?: Partial<WatchAppState>;
  /** Haptic feedback type */
  hapticFeedback?: 'success' | 'failure' | 'notification';
  /** Message to show (if any) */
  message?: string;
}

// =============================================================================
// Sync Types
// =============================================================================

/**
 * Full sync payload from phone to Watch
 */
export interface WatchSyncPayload {
  /** Current app state */
  state: WatchAppState;
  /** Complication data */
  complications: ComplicationData[];
  /** Timestamp of sync */
  syncTimestamp: string;
}

/**
 * Delta sync payload (incremental updates)
 */
export interface WatchDeltaSyncPayload {
  /** Fields that changed */
  changes: Partial<WatchAppState>;
  /** Updated complications (if any) */
  complications?: ComplicationData[];
  /** Timestamp */
  syncTimestamp: string;
}

// =============================================================================
// Connection State Types
// =============================================================================

/**
 * Watch connectivity state
 */
export interface WatchConnectivityState {
  /** Is Watch app installed */
  isWatchAppInstalled: boolean;
  /** Is Watch paired */
  isPaired: boolean;
  /** Is Watch reachable right now */
  isReachable: boolean;
  /** Session is active */
  isSessionActive: boolean;
  /** Last communication timestamp */
  lastCommunication: string | null;
  /** Any errors */
  error?: string;
}

// =============================================================================
// Exports
// =============================================================================

export default {
  // Type exports handled by `export type` above
};
