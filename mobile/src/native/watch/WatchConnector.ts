/**
 * DexAI Mobile - Watch Connector
 *
 * Manages Apple Watch communication via expo-watch-connectivity.
 * Handles:
 * - Sending current task data to Watch
 * - Receiving quick actions from Watch
 * - Updating complications
 * - Session management
 *
 * Note: This requires expo-watch-connectivity which may need native setup.
 * If the native module is not available, methods gracefully return errors.
 */

import { buildApiUrl, debugLog, debugError } from '../../utils/config';
import {
  WatchAppState,
  WatchConnectivityState,
  WatchMessage,
  WatchSyncPayload,
  WatchDeltaSyncPayload,
  QuickActionRequest,
  QuickActionResponse,
  ComplicationData,
  WatchTaskData,
} from './types';

// =============================================================================
// Module State
// =============================================================================

// Store watch connectivity module reference
let watchConnectivity: any = null;
let isModuleAvailable = false;

// Current state
let currentState: WatchAppState = {
  isPhoneReachable: true,
  currentTask: null,
  todayTaskCount: 0,
  energyLevel: 'unknown',
  inFlowState: false,
  lastSync: null,
  pendingActions: 0,
};

// Listeners
type StateChangeListener = (state: WatchAppState) => void;
type QuickActionListener = (action: QuickActionRequest) => Promise<QuickActionResponse>;

const stateChangeListeners: StateChangeListener[] = [];
let quickActionHandler: QuickActionListener | null = null;

// =============================================================================
// Initialization
// =============================================================================

/**
 * Initialize watch connectivity
 *
 * Call this during app initialization.
 */
export const initializeWatchConnectivity = async (): Promise<boolean> => {
  try {
    // Dynamically import to handle missing native module
    watchConnectivity = await import('expo-watch-connectivity').catch(() => null);

    if (!watchConnectivity) {
      debugLog('Watch: Module not available (expo-watch-connectivity not installed)');
      isModuleAvailable = false;
      return false;
    }

    isModuleAvailable = true;

    // Set up message listener
    if (watchConnectivity.addMessageListener) {
      watchConnectivity.addMessageListener(handleIncomingMessage);
    }

    // Set up reachability listener
    if (watchConnectivity.addReachabilityListener) {
      watchConnectivity.addReachabilityListener((reachable: boolean) => {
        debugLog('Watch: Reachability changed', reachable);
        updateState({ isPhoneReachable: reachable });
      });
    }

    debugLog('Watch: Connectivity initialized');
    return true;
  } catch (error) {
    debugError('Watch: Initialization failed', error);
    isModuleAvailable = false;
    return false;
  }
};

/**
 * Check if watch connectivity is available
 */
export const isWatchConnectivityAvailable = (): boolean => {
  return isModuleAvailable;
};

// =============================================================================
// Connectivity State
// =============================================================================

/**
 * Get current watch connectivity state
 */
export const getConnectivityState = async (): Promise<WatchConnectivityState> => {
  if (!isModuleAvailable) {
    return {
      isWatchAppInstalled: false,
      isPaired: false,
      isReachable: false,
      isSessionActive: false,
      lastCommunication: null,
      error: 'Watch connectivity not available',
    };
  }

  try {
    const isPaired = await watchConnectivity.getIsPaired?.() ?? false;
    const isWatchAppInstalled = await watchConnectivity.getIsWatchAppInstalled?.() ?? false;
    const isReachable = await watchConnectivity.getIsReachable?.() ?? false;

    return {
      isWatchAppInstalled,
      isPaired,
      isReachable,
      isSessionActive: isReachable,
      lastCommunication: currentState.lastSync,
    };
  } catch (error) {
    debugError('Watch: Failed to get connectivity state', error);
    return {
      isWatchAppInstalled: false,
      isPaired: false,
      isReachable: false,
      isSessionActive: false,
      lastCommunication: null,
      error: error instanceof Error ? error.message : 'Unknown error',
    };
  }
};

// =============================================================================
// State Management
// =============================================================================

/**
 * Update local state and notify listeners
 */
const updateState = (updates: Partial<WatchAppState>): void => {
  currentState = { ...currentState, ...updates };

  for (const listener of stateChangeListeners) {
    try {
      listener(currentState);
    } catch (error) {
      debugError('Watch: State listener error', error);
    }
  }
};

/**
 * Add state change listener
 */
export const addStateChangeListener = (listener: StateChangeListener): () => void => {
  stateChangeListeners.push(listener);
  return () => {
    const index = stateChangeListeners.indexOf(listener);
    if (index > -1) {
      stateChangeListeners.splice(index, 1);
    }
  };
};

/**
 * Get current state
 */
export const getCurrentState = (): WatchAppState => {
  return { ...currentState };
};

// =============================================================================
// Quick Actions
// =============================================================================

/**
 * Set handler for quick actions from Watch
 */
export const setQuickActionHandler = (handler: QuickActionListener): void => {
  quickActionHandler = handler;
};

/**
 * Default quick action handler that calls backend
 */
const defaultQuickActionHandler = async (
  action: QuickActionRequest
): Promise<QuickActionResponse> => {
  try {
    const response = await fetch(buildApiUrl('/api/mobile/quick-action/' + action.action), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task_id: action.taskId,
        duration_minutes: action.durationMinutes,
      }),
    });

    if (!response.ok) {
      throw new Error(`Server returned ${response.status}`);
    }

    const result = await response.json();

    return {
      success: result.success,
      newState: result.state,
      hapticFeedback: result.success ? 'success' : 'failure',
      message: result.message,
    };
  } catch (error) {
    debugError('Watch: Quick action failed', error);
    return {
      success: false,
      hapticFeedback: 'failure',
      message: 'Action failed',
    };
  }
};

// =============================================================================
// Message Handling
// =============================================================================

/**
 * Handle incoming message from Watch
 */
const handleIncomingMessage = async (message: WatchMessage): Promise<void> => {
  debugLog('Watch: Message received', message.type);

  switch (message.type) {
    case 'QUICK_ACTION':
      const actionRequest = message.payload as QuickActionRequest;
      const handler = quickActionHandler || defaultQuickActionHandler;
      const response = await handler(actionRequest);

      // Send response back to Watch
      await sendMessage({
        type: 'QUICK_ACTION',
        payload: response,
        timestamp: Date.now(),
        messageId: message.messageId,
      });

      // Update local state if needed
      if (response.newState) {
        updateState(response.newState);
      }
      break;

    case 'SYNC_STATE':
      // Watch is requesting current state
      await sendFullSync();
      break;

    case 'HEARTBEAT':
      // Update last communication time
      updateState({ lastSync: new Date().toISOString() });
      break;

    default:
      debugLog('Watch: Unknown message type', message.type);
  }
};

// =============================================================================
// Sending Data to Watch
// =============================================================================

/**
 * Send message to Watch
 */
export const sendMessage = async (message: WatchMessage): Promise<boolean> => {
  if (!isModuleAvailable) {
    debugLog('Watch: Cannot send message - module not available');
    return false;
  }

  try {
    const isReachable = await watchConnectivity.getIsReachable?.() ?? false;

    if (!isReachable) {
      debugLog('Watch: Cannot send message - not reachable');
      return false;
    }

    await watchConnectivity.sendMessage(message);
    updateState({ lastSync: new Date().toISOString() });
    debugLog('Watch: Message sent', message.type);
    return true;
  } catch (error) {
    debugError('Watch: Send message failed', error);
    return false;
  }
};

/**
 * Send full state sync to Watch
 */
export const sendFullSync = async (): Promise<boolean> => {
  try {
    // Fetch latest data from server
    const response = await fetch(buildApiUrl('/api/mobile/watch-data'), {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!response.ok) {
      throw new Error(`Server returned ${response.status}`);
    }

    const data = await response.json();

    // Build sync payload
    const payload: WatchSyncPayload = {
      state: {
        isPhoneReachable: true,
        currentTask: data.next_task ? formatTaskForWatch(data.next_task) : null,
        todayTaskCount: data.tasks_today || 0,
        energyLevel: data.energy_level || 'unknown',
        inFlowState: data.in_flow_state || false,
        lastSync: new Date().toISOString(),
        pendingActions: data.pending_actions || 0,
      },
      complications: data.complications || [],
      syncTimestamp: new Date().toISOString(),
    };

    // Update local state
    updateState(payload.state);

    // Send to Watch
    return await sendMessage({
      type: 'SYNC_STATE',
      payload,
      timestamp: Date.now(),
    });
  } catch (error) {
    debugError('Watch: Full sync failed', error);
    return false;
  }
};

/**
 * Send delta (incremental) update to Watch
 */
export const sendDeltaUpdate = async (
  changes: Partial<WatchAppState>,
  complications?: ComplicationData[]
): Promise<boolean> => {
  const payload: WatchDeltaSyncPayload = {
    changes,
    complications,
    syncTimestamp: new Date().toISOString(),
  };

  updateState(changes);

  return await sendMessage({
    type: 'TASK_UPDATE',
    payload,
    timestamp: Date.now(),
  });
};

/**
 * Update Watch complications
 */
export const updateComplications = async (
  complications: ComplicationData[]
): Promise<boolean> => {
  return await sendMessage({
    type: 'COMPLICATION_UPDATE',
    payload: { complications },
    timestamp: Date.now(),
  });
};

// =============================================================================
// Task Data Formatting
// =============================================================================

/**
 * Format task data for Watch display (truncated for small screen)
 */
const formatTaskForWatch = (task: any): WatchTaskData => {
  const maxTitleLength = 30;
  const maxStepLength = 50;

  let title = task.title || 'Untitled';
  if (title.length > maxTitleLength) {
    title = title.substring(0, maxTitleLength - 3) + '...';
  }

  let currentStep = task.current_step?.description || null;
  if (currentStep && currentStep.length > maxStepLength) {
    currentStep = currentStep.substring(0, maxStepLength - 3) + '...';
  }

  const stepNumber = task.current_step?.step_number;
  const totalSteps = task.current_step?.total_steps;
  const stepProgress = stepNumber && totalSteps ? `${stepNumber}/${totalSteps}` : null;

  return {
    id: task.id,
    title,
    currentStep,
    stepProgress,
    priority: task.priority || 5,
    dueTime: task.due_time || null,
    isOverdue: task.is_overdue || false,
  };
};

// =============================================================================
// Cleanup
// =============================================================================

/**
 * Clean up watch connectivity
 */
export const cleanupWatchConnectivity = (): void => {
  if (watchConnectivity?.removeMessageListener) {
    watchConnectivity.removeMessageListener(handleIncomingMessage);
  }

  stateChangeListeners.length = 0;
  quickActionHandler = null;

  debugLog('Watch: Cleaned up');
};

// =============================================================================
// Exports
// =============================================================================

export default {
  initializeWatchConnectivity,
  isWatchConnectivityAvailable,
  getConnectivityState,
  getCurrentState,
  addStateChangeListener,
  setQuickActionHandler,
  sendMessage,
  sendFullSync,
  sendDeltaUpdate,
  updateComplications,
  cleanupWatchConnectivity,
};
