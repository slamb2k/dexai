/**
 * DexAI Dashboard Library
 *
 * Central export point for all dashboard utilities.
 */

// Utilities
export * from './utils';

// API client
export { api, ApiClient, type ApiResponse, type DexStatus, type MetricsSummary } from './api';

// WebSocket client
export { socketClient, SocketClient } from './socket';

// State management
export {
  useDexStore,
  useActivityStore,
  useMetricsStore,
  useTasksStore,
  useSettingsStore,
  useToastStore,
  type Toast,
} from './store';
