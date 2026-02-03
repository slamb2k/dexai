/**
 * DexAI Mobile - Enhanced Background Sync Service
 *
 * Goes beyond basic background fetch to provide:
 * - Task synchronization
 * - Preference synchronization
 * - Notification sync
 * - Offline queue processing
 * - Conflict resolution
 */

import * as BackgroundFetch from 'expo-background-fetch';
import * as TaskManager from 'expo-task-manager';
import NetInfo, { NetInfoState } from '@react-native-community/netinfo';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { buildApiUrl, debugLog, debugError } from '../../utils/config';
import {
  setOnlineStatus,
  processQueue as processOfflineQueue,
  getQueueSize,
} from './OfflineQueue';

// =============================================================================
// Types
// =============================================================================

/**
 * Sync status for different data types
 */
export interface SyncStatus {
  tasks: SyncState;
  preferences: SyncState;
  notifications: SyncState;
  offlineQueue: SyncState;
}

/**
 * Individual sync state
 */
export interface SyncState {
  /** Last successful sync timestamp */
  lastSync: string | null;
  /** Is currently syncing */
  isSyncing: boolean;
  /** Error from last sync attempt */
  lastError: string | null;
  /** Number of pending changes */
  pendingChanges: number;
}

/**
 * Sync result
 */
export interface SyncResult {
  /** Overall success */
  success: boolean;
  /** Items synced */
  synced: number;
  /** Items with errors */
  errors: number;
  /** Conflicts detected */
  conflicts: number;
  /** Duration in ms */
  durationMs: number;
}

/**
 * Sync options
 */
export interface SyncOptions {
  /** Force sync even if recently synced */
  force?: boolean;
  /** Which data types to sync */
  dataTypes?: ('tasks' | 'preferences' | 'notifications')[];
  /** Process offline queue */
  processOfflineQueue?: boolean;
}

// =============================================================================
// Constants
// =============================================================================

const BACKGROUND_SYNC_TASK = 'dexai-background-sync';
const SYNC_STATUS_KEY = '@dexai_sync_status';
const MIN_SYNC_INTERVAL_MS = 5 * 60 * 1000; // 5 minutes

// =============================================================================
// Module State
// =============================================================================

let syncStatus: SyncStatus = {
  tasks: createDefaultSyncState(),
  preferences: createDefaultSyncState(),
  notifications: createDefaultSyncState(),
  offlineQueue: createDefaultSyncState(),
};

let isSyncing = false;

// Event listeners
type SyncListener = (status: SyncStatus, result?: SyncResult) => void;
const syncListeners: SyncListener[] = [];

// =============================================================================
// Background Task Definition
// =============================================================================

/**
 * Define the enhanced background sync task
 */
TaskManager.defineTask(BACKGROUND_SYNC_TASK, async () => {
  debugLog('BackgroundSync: Task started');

  try {
    const result = await performFullSync({ force: false });

    debugLog('BackgroundSync: Task completed', result);

    return result.success
      ? BackgroundFetch.BackgroundFetchResult.NewData
      : BackgroundFetch.BackgroundFetchResult.NoData;
  } catch (error) {
    debugError('BackgroundSync: Task failed', error);
    return BackgroundFetch.BackgroundFetchResult.Failed;
  }
});

// =============================================================================
// Initialization
// =============================================================================

/**
 * Initialize background sync service
 */
export const initializeBackgroundSync = async (): Promise<boolean> => {
  try {
    // Load saved sync status
    await loadSyncStatus();

    // Set up network listener
    NetInfo.addEventListener(handleNetworkChange);

    // Check initial network state
    const netState = await NetInfo.fetch();
    handleNetworkChange(netState);

    // Register background task
    const isRegistered = await TaskManager.isTaskRegisteredAsync(
      BACKGROUND_SYNC_TASK
    );

    if (!isRegistered) {
      await BackgroundFetch.registerTaskAsync(BACKGROUND_SYNC_TASK, {
        minimumInterval: 15 * 60, // 15 minutes
        stopOnTerminate: false,
        startOnBoot: true,
      });
    }

    debugLog('BackgroundSync: Initialized');
    return true;
  } catch (error) {
    debugError('BackgroundSync: Initialization failed', error);
    return false;
  }
};

/**
 * Handle network state changes
 */
const handleNetworkChange = (state: NetInfoState): void => {
  const isConnected = state.isConnected ?? false;
  setOnlineStatus(isConnected);

  debugLog('BackgroundSync: Network state', {
    connected: isConnected,
    type: state.type,
  });

  // Trigger sync when coming back online
  if (isConnected && !isSyncing) {
    // Small delay to let connection stabilize
    setTimeout(() => {
      performFullSync({ force: false });
    }, 2000);
  }
};

// =============================================================================
// Sync Operations
// =============================================================================

/**
 * Perform full sync
 */
export const performFullSync = async (
  options: SyncOptions = {}
): Promise<SyncResult> => {
  const startTime = Date.now();

  if (isSyncing) {
    debugLog('BackgroundSync: Already syncing');
    return {
      success: false,
      synced: 0,
      errors: 0,
      conflicts: 0,
      durationMs: 0,
    };
  }

  isSyncing = true;
  let totalSynced = 0;
  let totalErrors = 0;
  let totalConflicts = 0;

  try {
    const dataTypes = options.dataTypes || [
      'tasks',
      'preferences',
      'notifications',
    ];

    // Process offline queue first
    if (options.processOfflineQueue !== false) {
      const queueResult = await syncOfflineQueue();
      totalSynced += queueResult.synced;
      totalErrors += queueResult.errors;
    }

    // Sync each data type
    for (const dataType of dataTypes) {
      const shouldSync = options.force || shouldSyncDataType(dataType);

      if (!shouldSync) {
        debugLog('BackgroundSync: Skipping', dataType, '(recently synced)');
        continue;
      }

      let result: SyncResult;

      switch (dataType) {
        case 'tasks':
          result = await syncTasks();
          break;
        case 'preferences':
          result = await syncPreferences();
          break;
        case 'notifications':
          result = await syncNotifications();
          break;
        default:
          continue;
      }

      totalSynced += result.synced;
      totalErrors += result.errors;
      totalConflicts += result.conflicts;
    }

    await saveSyncStatus();
    notifyListeners();

    const durationMs = Date.now() - startTime;

    debugLog('BackgroundSync: Complete', {
      synced: totalSynced,
      errors: totalErrors,
      conflicts: totalConflicts,
      durationMs,
    });

    return {
      success: totalErrors === 0,
      synced: totalSynced,
      errors: totalErrors,
      conflicts: totalConflicts,
      durationMs,
    };
  } catch (error) {
    debugError('BackgroundSync: Failed', error);
    return {
      success: false,
      synced: totalSynced,
      errors: totalErrors + 1,
      conflicts: totalConflicts,
      durationMs: Date.now() - startTime,
    };
  } finally {
    isSyncing = false;
  }
};

/**
 * Sync offline queue
 */
const syncOfflineQueue = async (): Promise<SyncResult> => {
  updateSyncState('offlineQueue', { isSyncing: true });

  try {
    const queueSize = getQueueSize();

    if (queueSize === 0) {
      updateSyncState('offlineQueue', {
        isSyncing: false,
        lastSync: new Date().toISOString(),
        pendingChanges: 0,
      });
      return { success: true, synced: 0, errors: 0, conflicts: 0, durationMs: 0 };
    }

    const results = await processOfflineQueue();

    const synced = results.filter((r) => r.success).length;
    const errors = results.filter((r) => !r.success && !r.skippedDueToConflict)
      .length;
    const conflicts = results.filter((r) => r.skippedDueToConflict).length;

    updateSyncState('offlineQueue', {
      isSyncing: false,
      lastSync: new Date().toISOString(),
      lastError: errors > 0 ? `${errors} actions failed` : null,
      pendingChanges: getQueueSize(),
    });

    return { success: errors === 0, synced, errors, conflicts, durationMs: 0 };
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : 'Unknown error';
    updateSyncState('offlineQueue', {
      isSyncing: false,
      lastError: errorMsg,
    });
    return { success: false, synced: 0, errors: 1, conflicts: 0, durationMs: 0 };
  }
};

/**
 * Sync tasks with server
 */
const syncTasks = async (): Promise<SyncResult> => {
  updateSyncState('tasks', { isSyncing: true });

  try {
    const response = await fetch(buildApiUrl('/api/tasks/sync'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        last_sync: syncStatus.tasks.lastSync,
      }),
    });

    if (!response.ok) {
      throw new Error(`Server returned ${response.status}`);
    }

    const data = await response.json();

    updateSyncState('tasks', {
      isSyncing: false,
      lastSync: new Date().toISOString(),
      lastError: null,
      pendingChanges: 0,
    });

    return {
      success: true,
      synced: data.synced || 0,
      errors: 0,
      conflicts: data.conflicts || 0,
      durationMs: 0,
    };
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : 'Unknown error';
    updateSyncState('tasks', {
      isSyncing: false,
      lastError: errorMsg,
    });
    return { success: false, synced: 0, errors: 1, conflicts: 0, durationMs: 0 };
  }
};

/**
 * Sync preferences with server
 */
const syncPreferences = async (): Promise<SyncResult> => {
  updateSyncState('preferences', { isSyncing: true });

  try {
    const response = await fetch(buildApiUrl('/api/push/preferences'), {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!response.ok) {
      throw new Error(`Server returned ${response.status}`);
    }

    const data = await response.json();

    // Store preferences locally
    await AsyncStorage.setItem('@dexai_preferences', JSON.stringify(data));

    updateSyncState('preferences', {
      isSyncing: false,
      lastSync: new Date().toISOString(),
      lastError: null,
      pendingChanges: 0,
    });

    return { success: true, synced: 1, errors: 0, conflicts: 0, durationMs: 0 };
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : 'Unknown error';
    updateSyncState('preferences', {
      isSyncing: false,
      lastError: errorMsg,
    });
    return { success: false, synced: 0, errors: 1, conflicts: 0, durationMs: 0 };
  }
};

/**
 * Sync notifications with server
 */
const syncNotifications = async (): Promise<SyncResult> => {
  updateSyncState('notifications', { isSyncing: true });

  try {
    const response = await fetch(buildApiUrl('/api/push/sync'), {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!response.ok) {
      throw new Error(`Server returned ${response.status}`);
    }

    const data = await response.json();

    updateSyncState('notifications', {
      isSyncing: false,
      lastSync: new Date().toISOString(),
      lastError: null,
      pendingChanges: data.pendingNotifications?.length || 0,
    });

    return {
      success: true,
      synced: data.pendingNotifications?.length || 0,
      errors: 0,
      conflicts: 0,
      durationMs: 0,
    };
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : 'Unknown error';
    updateSyncState('notifications', {
      isSyncing: false,
      lastError: errorMsg,
    });
    return { success: false, synced: 0, errors: 1, conflicts: 0, durationMs: 0 };
  }
};

// =============================================================================
// State Management
// =============================================================================

/**
 * Check if data type needs syncing
 */
const shouldSyncDataType = (dataType: string): boolean => {
  const state = syncStatus[dataType as keyof SyncStatus];
  if (!state || !state.lastSync) return true;

  const lastSyncTime = new Date(state.lastSync).getTime();
  const now = Date.now();

  return now - lastSyncTime > MIN_SYNC_INTERVAL_MS;
};

/**
 * Update sync state for a data type
 */
const updateSyncState = (
  dataType: keyof SyncStatus,
  updates: Partial<SyncState>
): void => {
  syncStatus[dataType] = { ...syncStatus[dataType], ...updates };
};

/**
 * Create default sync state
 */
function createDefaultSyncState(): SyncState {
  return {
    lastSync: null,
    isSyncing: false,
    lastError: null,
    pendingChanges: 0,
  };
}

/**
 * Get current sync status
 */
export const getSyncStatus = (): SyncStatus => {
  return { ...syncStatus };
};

/**
 * Get sync status for specific data type
 */
export const getDataTypeSyncStatus = (
  dataType: keyof SyncStatus
): SyncState => {
  return { ...syncStatus[dataType] };
};

// =============================================================================
// Persistence
// =============================================================================

/**
 * Load sync status from storage
 */
const loadSyncStatus = async (): Promise<void> => {
  try {
    const stored = await AsyncStorage.getItem(SYNC_STATUS_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      syncStatus = {
        tasks: { ...createDefaultSyncState(), ...parsed.tasks },
        preferences: { ...createDefaultSyncState(), ...parsed.preferences },
        notifications: { ...createDefaultSyncState(), ...parsed.notifications },
        offlineQueue: { ...createDefaultSyncState(), ...parsed.offlineQueue },
      };
    }
  } catch (error) {
    debugError('BackgroundSync: Failed to load status', error);
  }
};

/**
 * Save sync status to storage
 */
const saveSyncStatus = async (): Promise<void> => {
  try {
    await AsyncStorage.setItem(SYNC_STATUS_KEY, JSON.stringify(syncStatus));
  } catch (error) {
    debugError('BackgroundSync: Failed to save status', error);
  }
};

// =============================================================================
// Event Listeners
// =============================================================================

/**
 * Add sync listener
 */
export const addSyncListener = (listener: SyncListener): (() => void) => {
  syncListeners.push(listener);
  return () => {
    const index = syncListeners.indexOf(listener);
    if (index > -1) {
      syncListeners.splice(index, 1);
    }
  };
};

/**
 * Notify all listeners
 */
const notifyListeners = (result?: SyncResult): void => {
  for (const listener of syncListeners) {
    try {
      listener({ ...syncStatus }, result);
    } catch (error) {
      debugError('BackgroundSync: Listener error', error);
    }
  }
};

// =============================================================================
// Manual Sync Triggers
// =============================================================================

/**
 * Trigger manual sync for specific data type
 */
export const syncDataType = async (
  dataType: 'tasks' | 'preferences' | 'notifications'
): Promise<SyncResult> => {
  return performFullSync({
    force: true,
    dataTypes: [dataType],
    processOfflineQueue: false,
  });
};

/**
 * Force full sync
 */
export const forceSync = async (): Promise<SyncResult> => {
  return performFullSync({ force: true });
};

// =============================================================================
// Cleanup
// =============================================================================

/**
 * Clean up background sync
 */
export const cleanupBackgroundSync = async (): Promise<void> => {
  try {
    await TaskManager.unregisterTaskAsync(BACKGROUND_SYNC_TASK);
  } catch {
    // Task might not be registered
  }

  syncListeners.length = 0;
  debugLog('BackgroundSync: Cleaned up');
};

// =============================================================================
// Exports
// =============================================================================

export default {
  initializeBackgroundSync,
  performFullSync,
  getSyncStatus,
  getDataTypeSyncStatus,
  addSyncListener,
  syncDataType,
  forceSync,
  cleanupBackgroundSync,
  BACKGROUND_SYNC_TASK,
};
