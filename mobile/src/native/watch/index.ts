/**
 * DexAI Mobile - Watch Exports
 *
 * Apple Watch communication and data sync.
 */

export {
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
} from './WatchConnector';

export type {
  WatchMessageType,
  WatchMessage,
  WatchTaskData,
  WatchAppState,
  ComplicationData,
  ComplicationType,
  ComplicationDisplayData,
  QuickActionType,
  QuickActionRequest,
  QuickActionResponse,
  WatchSyncPayload,
  WatchDeltaSyncPayload,
  WatchConnectivityState,
} from './types';
