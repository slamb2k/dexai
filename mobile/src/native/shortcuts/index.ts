/**
 * DexAI Mobile - Shortcuts Exports
 *
 * Siri Shortcuts and 3D Touch Quick Actions.
 */

// Siri Shortcuts
export {
  initializeSiriShortcuts,
  isSiriAvailable,
  registerShortcut,
  unregisterShortcut,
  getRegisteredShortcuts,
  setShortcutHandler,
  donateActivity,
  donateTaskViewActivity,
  donateTaskCompletionActivity,
  presentAddToSiri,
  cleanupSiriShortcuts,
  DEFAULT_SHORTCUTS,
  type ShortcutId,
  type ShortcutDefinition,
  type ShortcutResult,
  type UserActivity,
} from './SiriShortcuts';

// Quick Actions (3D Touch / Long Press)
export {
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
  type QuickActionId,
  type QuickAction,
  type QuickActionInvocation,
  type QuickActionResult,
} from './QuickActions';
