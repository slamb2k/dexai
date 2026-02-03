/**
 * DexAI Mobile - Quick Actions (3D Touch / Long Press)
 *
 * Provides quick actions on the app icon:
 * - "Next Task" - open to current task
 * - "Quick Capture" - add task quickly
 * - "Focus Mode" - enable DND and flow state
 *
 * Also supports dynamic shortcuts based on recent activity.
 *
 * Note: Requires expo-quick-actions or react-native-quick-actions.
 */

import { Platform, Linking } from 'react-native';
import { buildApiUrl, debugLog, debugError } from '../../utils/config';

// =============================================================================
// Types
// =============================================================================

/**
 * Quick action identifiers
 */
export type QuickActionId =
  | 'next_task'
  | 'quick_capture'
  | 'focus_mode'
  | 'recent_task'; // Dynamic action for recently viewed task

/**
 * Quick action definition
 */
export interface QuickAction {
  /** Unique identifier */
  id: QuickActionId | string;
  /** Display title */
  title: string;
  /** Short subtitle */
  subtitle?: string;
  /** Icon name (SF Symbol on iOS, material icon on Android) */
  icon: string;
  /** Icon type */
  iconType: 'system' | 'custom';
  /** User data payload */
  userInfo?: Record<string, unknown>;
  /** Is this a dynamic (mutable) shortcut */
  isDynamic: boolean;
}

/**
 * Quick action invocation
 */
export interface QuickActionInvocation {
  /** Action identifier */
  id: QuickActionId | string;
  /** User data */
  userInfo?: Record<string, unknown>;
  /** Timestamp */
  timestamp: number;
}

/**
 * Quick action handler result
 */
export interface QuickActionResult {
  /** Whether action was handled */
  handled: boolean;
  /** Navigation path (if app should navigate) */
  navigateTo?: string;
  /** Show alert message */
  alertMessage?: string;
}

// =============================================================================
// Module State
// =============================================================================

let quickActions: any = null;
let isModuleAvailable = false;

// Action handler
type QuickActionHandler = (action: QuickActionInvocation) => Promise<QuickActionResult>;
let actionHandler: QuickActionHandler | null = null;

// Pending action (if app was launched via quick action)
let pendingAction: QuickActionInvocation | null = null;

// =============================================================================
// Default Quick Actions
// =============================================================================

export const DEFAULT_QUICK_ACTIONS: QuickAction[] = [
  {
    id: 'next_task',
    title: 'Next Task',
    subtitle: 'See what to do next',
    icon: Platform.OS === 'ios' ? 'checklist' : 'checklist',
    iconType: 'system',
    isDynamic: false,
  },
  {
    id: 'quick_capture',
    title: 'Quick Capture',
    subtitle: 'Add a task',
    icon: Platform.OS === 'ios' ? 'plus.circle.fill' : 'add_circle',
    iconType: 'system',
    isDynamic: false,
  },
  {
    id: 'focus_mode',
    title: 'Focus Mode',
    subtitle: 'Start focusing',
    icon: Platform.OS === 'ios' ? 'scope' : 'center_focus_strong',
    iconType: 'system',
    isDynamic: false,
  },
];

// =============================================================================
// Initialization
// =============================================================================

/**
 * Initialize quick actions
 */
export const initializeQuickActions = async (): Promise<boolean> => {
  try {
    // Try to import the native module
    quickActions = await import('expo-quick-actions').catch(() => null);

    if (!quickActions) {
      // Try alternative module
      quickActions = await import('react-native-quick-actions').catch(() => null);
    }

    if (!quickActions) {
      debugLog('QuickActions: Module not available');
      isModuleAvailable = false;
      return false;
    }

    isModuleAvailable = true;

    // Set up listener for quick action invocations
    if (quickActions.setQuickActionHandler) {
      quickActions.setQuickActionHandler(handleQuickActionPress);
    } else if (quickActions.popInitialAction) {
      // Handle initial action (app launched via quick action)
      const initialAction = await quickActions.popInitialAction();
      if (initialAction) {
        pendingAction = {
          id: initialAction.type || initialAction.shortcutType,
          userInfo: initialAction.userInfo,
          timestamp: Date.now(),
        };
      }
    }

    // Set initial actions
    await setQuickActions(DEFAULT_QUICK_ACTIONS);

    debugLog('QuickActions: Initialized');
    return true;
  } catch (error) {
    debugError('QuickActions: Initialization failed', error);
    isModuleAvailable = false;
    return false;
  }
};

/**
 * Check if quick actions are available
 */
export const isQuickActionsAvailable = (): boolean => {
  return isModuleAvailable;
};

// =============================================================================
// Quick Action Management
// =============================================================================

/**
 * Set quick actions on app icon
 */
export const setQuickActions = async (actions: QuickAction[]): Promise<boolean> => {
  if (!isModuleAvailable) {
    debugLog('QuickActions: Cannot set actions - module not available');
    return false;
  }

  try {
    const formattedActions = actions.map((action) => ({
      type: action.id,
      title: action.title,
      subtitle: action.subtitle,
      icon: action.icon,
      iconType: action.iconType,
      userInfo: action.userInfo || {},
    }));

    if (quickActions.setShortcutItems) {
      await quickActions.setShortcutItems(formattedActions);
    } else if (quickActions.setQuickActions) {
      await quickActions.setQuickActions(formattedActions);
    }

    debugLog('QuickActions: Set', actions.length, 'actions');
    return true;
  } catch (error) {
    debugError('QuickActions: Failed to set actions', error);
    return false;
  }
};

/**
 * Clear all quick actions
 */
export const clearQuickActions = async (): Promise<boolean> => {
  if (!isModuleAvailable) return true;

  try {
    if (quickActions.clearShortcutItems) {
      await quickActions.clearShortcutItems();
    } else if (quickActions.setQuickActions) {
      await quickActions.setQuickActions([]);
    }

    debugLog('QuickActions: Cleared');
    return true;
  } catch (error) {
    debugError('QuickActions: Failed to clear', error);
    return false;
  }
};

/**
 * Add a dynamic quick action (e.g., recent task)
 */
export const addDynamicAction = async (action: QuickAction): Promise<boolean> => {
  if (!isModuleAvailable) return false;

  try {
    // Get current actions
    const currentActions = await getCurrentActions();

    // Remove any existing action with same ID
    const filteredActions = currentActions.filter((a) => a.id !== action.id);

    // Add new dynamic action at the beginning (after static actions)
    const staticCount = DEFAULT_QUICK_ACTIONS.length;
    const newActions = [
      ...filteredActions.slice(0, staticCount),
      { ...action, isDynamic: true },
      ...filteredActions.slice(staticCount),
    ];

    // Limit to 4 actions (iOS limit)
    const limitedActions = newActions.slice(0, 4);

    await setQuickActions(limitedActions);
    debugLog('QuickActions: Added dynamic action', action.id);
    return true;
  } catch (error) {
    debugError('QuickActions: Failed to add dynamic action', error);
    return false;
  }
};

/**
 * Remove a dynamic quick action
 */
export const removeDynamicAction = async (actionId: string): Promise<boolean> => {
  if (!isModuleAvailable) return true;

  try {
    const currentActions = await getCurrentActions();
    const filteredActions = currentActions.filter((a) => a.id !== actionId);

    await setQuickActions(filteredActions);
    debugLog('QuickActions: Removed dynamic action', actionId);
    return true;
  } catch (error) {
    debugError('QuickActions: Failed to remove dynamic action', error);
    return false;
  }
};

/**
 * Get current quick actions
 */
const getCurrentActions = async (): Promise<QuickAction[]> => {
  // Return default actions as base (we track dynamic ones separately)
  return [...DEFAULT_QUICK_ACTIONS];
};

// =============================================================================
// Action Handler
// =============================================================================

/**
 * Set custom quick action handler
 */
export const setQuickActionHandler = (handler: QuickActionHandler): void => {
  actionHandler = handler;
};

/**
 * Handle quick action press
 */
const handleQuickActionPress = async (data: any): Promise<void> => {
  const actionId = data?.type || data?.shortcutType;

  if (!actionId) {
    debugError('QuickActions: Invalid action data', data);
    return;
  }

  const invocation: QuickActionInvocation = {
    id: actionId,
    userInfo: data?.userInfo,
    timestamp: Date.now(),
  };

  debugLog('QuickActions: Action pressed', actionId);

  const handler = actionHandler || defaultActionHandler;
  const result = await handler(invocation);

  // Handle navigation if needed
  if (result.navigateTo) {
    Linking.openURL(`dexai://${result.navigateTo}`);
  }
};

/**
 * Default action handler that calls backend
 */
const defaultActionHandler = async (
  action: QuickActionInvocation
): Promise<QuickActionResult> => {
  try {
    const response = await fetch(
      buildApiUrl(`/api/mobile/quick-action/${action.id}`),
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_info: action.userInfo,
        }),
      }
    );

    if (!response.ok) {
      throw new Error(`Server returned ${response.status}`);
    }

    const result = await response.json();

    return {
      handled: result.success,
      navigateTo: result.navigate_to,
      alertMessage: result.message,
    };
  } catch (error) {
    debugError('QuickActions: Handler failed', error);

    // Fall back to default navigation
    return getDefaultNavigation(action.id as QuickActionId);
  }
};

/**
 * Get default navigation for action
 */
const getDefaultNavigation = (actionId: QuickActionId): QuickActionResult => {
  switch (actionId) {
    case 'next_task':
      return { handled: true, navigateTo: 'tasks/current' };
    case 'quick_capture':
      return { handled: true, navigateTo: 'tasks/add' };
    case 'focus_mode':
      return { handled: true, navigateTo: 'focus' };
    case 'recent_task':
      return { handled: true, navigateTo: 'tasks' };
    default:
      return { handled: false };
  }
};

// =============================================================================
// Pending Action
// =============================================================================

/**
 * Get and clear pending action (from app launch)
 */
export const getPendingAction = (): QuickActionInvocation | null => {
  const action = pendingAction;
  pendingAction = null;
  return action;
};

/**
 * Check if there's a pending action
 */
export const hasPendingAction = (): boolean => {
  return pendingAction !== null;
};

// =============================================================================
// Dynamic Actions Based on Activity
// =============================================================================

/**
 * Update quick actions based on recent task
 */
export const updateRecentTaskAction = async (
  taskId: string,
  taskTitle: string
): Promise<boolean> => {
  const shortTitle =
    taskTitle.length > 25 ? taskTitle.substring(0, 22) + '...' : taskTitle;

  return addDynamicAction({
    id: `recent_task_${taskId}`,
    title: shortTitle,
    subtitle: 'Continue task',
    icon: Platform.OS === 'ios' ? 'arrow.right.circle' : 'arrow_forward',
    iconType: 'system',
    userInfo: { taskId },
    isDynamic: true,
  });
};

/**
 * Refresh dynamic actions from server
 */
export const refreshDynamicActions = async (): Promise<boolean> => {
  try {
    const response = await fetch(buildApiUrl('/api/mobile/shortcuts/suggested'), {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!response.ok) {
      throw new Error(`Server returned ${response.status}`);
    }

    const data = await response.json();

    if (data.shortcuts && Array.isArray(data.shortcuts)) {
      // Start with static actions
      const actions = [...DEFAULT_QUICK_ACTIONS];

      // Add suggested dynamic actions
      for (const shortcut of data.shortcuts.slice(0, 1)) {
        actions.push({
          id: shortcut.id,
          title: shortcut.title,
          subtitle: shortcut.subtitle,
          icon: shortcut.icon || (Platform.OS === 'ios' ? 'star.fill' : 'star'),
          iconType: 'system',
          userInfo: shortcut.user_info,
          isDynamic: true,
        });
      }

      await setQuickActions(actions);
    }

    return true;
  } catch (error) {
    debugError('QuickActions: Failed to refresh dynamic actions', error);
    return false;
  }
};

// =============================================================================
// Cleanup
// =============================================================================

/**
 * Clean up quick actions
 */
export const cleanupQuickActions = (): void => {
  actionHandler = null;
  pendingAction = null;
  debugLog('QuickActions: Cleaned up');
};

// =============================================================================
// Exports
// =============================================================================

export default {
  initializeQuickActions,
  isQuickActionsAvailable,
  setQuickActions,
  clearQuickActions,
  addDynamicAction,
  removeDynamicAction,
  setQuickActionHandler,
  getPendingAction,
  hasPendingAction,
  updateRecentTaskAction,
  refreshDynamicActions,
  cleanupQuickActions,
  DEFAULT_QUICK_ACTIONS,
};
