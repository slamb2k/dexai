/**
 * DexAI Mobile - Offline Queue
 *
 * Queues actions when offline and replays them when connectivity is restored.
 * Features:
 * - Persist queue to AsyncStorage
 * - Automatic replay on reconnection
 * - Conflict detection and resolution
 * - Exponential backoff for retries
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { buildApiUrl, debugLog, debugError } from '../../utils/config';

// =============================================================================
// Types
// =============================================================================

/**
 * Action types that can be queued
 */
export type QueuedActionType =
  | 'task_complete' // Complete a task
  | 'task_update' // Update task details
  | 'step_complete' // Complete a step
  | 'task_create' // Create new task
  | 'preference_update' // Update preferences
  | 'notification_ack' // Acknowledge notification
  | 'focus_start' // Start focus session
  | 'focus_end'; // End focus session

/**
 * Queued action
 */
export interface QueuedAction {
  /** Unique action ID */
  id: string;
  /** Action type */
  type: QueuedActionType;
  /** API endpoint path */
  endpoint: string;
  /** HTTP method */
  method: 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  /** Request payload */
  payload: Record<string, unknown>;
  /** When action was queued */
  queuedAt: string;
  /** Number of retry attempts */
  retryCount: number;
  /** Last retry timestamp */
  lastRetryAt?: string;
  /** Priority (higher = more important) */
  priority: number;
  /** Entity ID for conflict detection */
  entityId?: string;
  /** Entity version for conflict detection */
  entityVersion?: number;
  /** Should skip if conflict detected */
  skipOnConflict: boolean;
}

/**
 * Queue state
 */
export interface QueueState {
  /** Pending actions */
  actions: QueuedAction[];
  /** Last successful sync */
  lastSync: string | null;
  /** Is currently processing */
  isProcessing: boolean;
  /** Failed action IDs */
  failedActions: string[];
}

/**
 * Action result
 */
export interface ActionResult {
  /** Action ID */
  actionId: string;
  /** Whether action succeeded */
  success: boolean;
  /** Error message if failed */
  error?: string;
  /** Was action skipped due to conflict */
  skippedDueToConflict?: boolean;
  /** Server response */
  response?: unknown;
}

// =============================================================================
// Constants
// =============================================================================

const STORAGE_KEY = '@dexai_offline_queue';
const MAX_RETRY_COUNT = 5;
const BASE_RETRY_DELAY_MS = 1000;
const MAX_QUEUE_SIZE = 100;

// =============================================================================
// Module State
// =============================================================================

let queueState: QueueState = {
  actions: [],
  lastSync: null,
  isProcessing: false,
  failedActions: [],
};

// Event listeners
type QueueChangeListener = (state: QueueState) => void;
const queueChangeListeners: QueueChangeListener[] = [];

// Connectivity tracking
let isOnline = true;

// =============================================================================
// Persistence
// =============================================================================

/**
 * Load queue from storage
 */
export const loadQueue = async (): Promise<void> => {
  try {
    const stored = await AsyncStorage.getItem(STORAGE_KEY);

    if (stored) {
      const parsed = JSON.parse(stored);
      queueState = {
        ...queueState,
        actions: parsed.actions || [],
        lastSync: parsed.lastSync || null,
        failedActions: parsed.failedActions || [],
      };

      debugLog('OfflineQueue: Loaded', queueState.actions.length, 'actions');
    }
  } catch (error) {
    debugError('OfflineQueue: Failed to load', error);
  }
};

/**
 * Save queue to storage
 */
const saveQueue = async (): Promise<void> => {
  try {
    await AsyncStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        actions: queueState.actions,
        lastSync: queueState.lastSync,
        failedActions: queueState.failedActions,
      })
    );
  } catch (error) {
    debugError('OfflineQueue: Failed to save', error);
  }
};

// =============================================================================
// Queue Operations
// =============================================================================

/**
 * Add action to queue
 */
export const enqueueAction = async (
  type: QueuedActionType,
  endpoint: string,
  method: 'POST' | 'PUT' | 'DELETE' | 'PATCH',
  payload: Record<string, unknown>,
  options: {
    priority?: number;
    entityId?: string;
    entityVersion?: number;
    skipOnConflict?: boolean;
  } = {}
): Promise<string> => {
  // Generate unique ID
  const id = `${type}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

  const action: QueuedAction = {
    id,
    type,
    endpoint,
    method,
    payload,
    queuedAt: new Date().toISOString(),
    retryCount: 0,
    priority: options.priority ?? 5,
    entityId: options.entityId,
    entityVersion: options.entityVersion,
    skipOnConflict: options.skipOnConflict ?? false,
  };

  // Check queue size
  if (queueState.actions.length >= MAX_QUEUE_SIZE) {
    // Remove lowest priority items
    queueState.actions.sort((a, b) => b.priority - a.priority);
    queueState.actions = queueState.actions.slice(0, MAX_QUEUE_SIZE - 1);
  }

  // Add action
  queueState.actions.push(action);
  await saveQueue();
  notifyListeners();

  debugLog('OfflineQueue: Enqueued', type, id);

  // If online, try to process immediately
  if (isOnline && !queueState.isProcessing) {
    processQueue();
  }

  return id;
};

/**
 * Remove action from queue
 */
export const removeAction = async (actionId: string): Promise<boolean> => {
  const index = queueState.actions.findIndex((a) => a.id === actionId);

  if (index === -1) {
    return false;
  }

  queueState.actions.splice(index, 1);
  await saveQueue();
  notifyListeners();

  debugLog('OfflineQueue: Removed', actionId);
  return true;
};

/**
 * Clear all actions
 */
export const clearQueue = async (): Promise<void> => {
  queueState.actions = [];
  queueState.failedActions = [];
  await saveQueue();
  notifyListeners();

  debugLog('OfflineQueue: Cleared');
};

/**
 * Get pending actions
 */
export const getPendingActions = (): QueuedAction[] => {
  return [...queueState.actions];
};

/**
 * Get queue size
 */
export const getQueueSize = (): number => {
  return queueState.actions.length;
};

// =============================================================================
// Queue Processing
// =============================================================================

/**
 * Process queued actions
 */
export const processQueue = async (): Promise<ActionResult[]> => {
  if (queueState.isProcessing) {
    debugLog('OfflineQueue: Already processing');
    return [];
  }

  if (queueState.actions.length === 0) {
    debugLog('OfflineQueue: Nothing to process');
    return [];
  }

  if (!isOnline) {
    debugLog('OfflineQueue: Offline, skipping');
    return [];
  }

  queueState.isProcessing = true;
  notifyListeners();

  const results: ActionResult[] = [];

  // Sort by priority (highest first)
  const sortedActions = [...queueState.actions].sort(
    (a, b) => b.priority - a.priority
  );

  for (const action of sortedActions) {
    const result = await processAction(action);
    results.push(result);

    if (result.success || result.skippedDueToConflict) {
      // Remove from queue
      await removeAction(action.id);
    } else if (action.retryCount >= MAX_RETRY_COUNT) {
      // Max retries reached, move to failed
      await removeAction(action.id);
      queueState.failedActions.push(action.id);
    }
  }

  queueState.isProcessing = false;
  queueState.lastSync = new Date().toISOString();
  await saveQueue();
  notifyListeners();

  debugLog('OfflineQueue: Processed', results.length, 'actions');
  return results;
};

/**
 * Process single action
 */
const processAction = async (action: QueuedAction): Promise<ActionResult> => {
  try {
    // Check for conflicts if entity tracking is enabled
    if (action.entityId && action.entityVersion !== undefined) {
      const hasConflict = await checkForConflict(action);
      if (hasConflict) {
        debugLog('OfflineQueue: Conflict detected for', action.id);
        if (action.skipOnConflict) {
          return {
            actionId: action.id,
            success: false,
            skippedDueToConflict: true,
            error: 'Skipped due to conflict',
          };
        }
      }
    }

    // Calculate delay for retries
    if (action.retryCount > 0) {
      const delay = BASE_RETRY_DELAY_MS * Math.pow(2, action.retryCount - 1);
      await sleep(delay);
    }

    // Make request
    const response = await fetch(buildApiUrl(action.endpoint), {
      method: action.method,
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(action.payload),
    });

    if (!response.ok) {
      throw new Error(`Server returned ${response.status}`);
    }

    const data = await response.json();

    return {
      actionId: action.id,
      success: true,
      response: data,
    };
  } catch (error) {
    // Update retry count
    action.retryCount++;
    action.lastRetryAt = new Date().toISOString();

    debugError('OfflineQueue: Action failed', action.id, error);

    return {
      actionId: action.id,
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error',
    };
  }
};

/**
 * Check for conflict with server state
 */
const checkForConflict = async (action: QueuedAction): Promise<boolean> => {
  if (!action.entityId) return false;

  try {
    // Fetch current entity version from server
    const response = await fetch(
      buildApiUrl(`/api/entity/${action.entityId}/version`),
      {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
      }
    );

    if (!response.ok) {
      // If we can't check, assume no conflict
      return false;
    }

    const data = await response.json();
    const serverVersion = data.version;

    // If server version is newer, we have a conflict
    return (
      action.entityVersion !== undefined && serverVersion > action.entityVersion
    );
  } catch {
    // If we can't check, assume no conflict
    return false;
  }
};

// =============================================================================
// Connectivity
// =============================================================================

/**
 * Update online status
 */
export const setOnlineStatus = (online: boolean): void => {
  const wasOffline = !isOnline;
  isOnline = online;

  debugLog('OfflineQueue: Online status', online);

  // If coming back online, process queue
  if (online && wasOffline && queueState.actions.length > 0) {
    debugLog('OfflineQueue: Back online, processing queue');
    processQueue();
  }
};

/**
 * Get online status
 */
export const getOnlineStatus = (): boolean => {
  return isOnline;
};

// =============================================================================
// Event Listeners
// =============================================================================

/**
 * Add queue change listener
 */
export const addQueueChangeListener = (
  listener: QueueChangeListener
): (() => void) => {
  queueChangeListeners.push(listener);
  return () => {
    const index = queueChangeListeners.indexOf(listener);
    if (index > -1) {
      queueChangeListeners.splice(index, 1);
    }
  };
};

/**
 * Notify all listeners of state change
 */
const notifyListeners = (): void => {
  for (const listener of queueChangeListeners) {
    try {
      listener({ ...queueState });
    } catch (error) {
      debugError('OfflineQueue: Listener error', error);
    }
  }
};

// =============================================================================
// Convenience Methods
// =============================================================================

/**
 * Queue task completion
 */
export const queueTaskComplete = async (
  taskId: string,
  version?: number
): Promise<string> => {
  return enqueueAction(
    'task_complete',
    `/api/tasks/${taskId}/complete`,
    'POST',
    { completed_at: new Date().toISOString() },
    {
      priority: 8,
      entityId: taskId,
      entityVersion: version,
      skipOnConflict: false, // Task completion should always apply
    }
  );
};

/**
 * Queue step completion
 */
export const queueStepComplete = async (
  taskId: string,
  stepNumber: number
): Promise<string> => {
  return enqueueAction(
    'step_complete',
    `/api/tasks/${taskId}/steps/${stepNumber}/complete`,
    'POST',
    { completed_at: new Date().toISOString() },
    { priority: 7 }
  );
};

/**
 * Queue task update
 */
export const queueTaskUpdate = async (
  taskId: string,
  updates: Record<string, unknown>,
  version?: number
): Promise<string> => {
  return enqueueAction('task_update', `/api/tasks/${taskId}`, 'PATCH', updates, {
    priority: 6,
    entityId: taskId,
    entityVersion: version,
    skipOnConflict: true, // Skip if task was modified by another client
  });
};

/**
 * Queue notification acknowledgment
 */
export const queueNotificationAck = async (
  notificationId: string
): Promise<string> => {
  return enqueueAction(
    'notification_ack',
    `/api/push/track/delivered`,
    'POST',
    { notification_id: notificationId },
    { priority: 3 }
  );
};

// =============================================================================
// Utilities
// =============================================================================

const sleep = (ms: number): Promise<void> => {
  return new Promise((resolve) => setTimeout(resolve, ms));
};

// =============================================================================
// Exports
// =============================================================================

export default {
  loadQueue,
  enqueueAction,
  removeAction,
  clearQueue,
  getPendingActions,
  getQueueSize,
  processQueue,
  setOnlineStatus,
  getOnlineStatus,
  addQueueChangeListener,
  queueTaskComplete,
  queueStepComplete,
  queueTaskUpdate,
  queueNotificationAck,
};
