/**
 * DexAI Mobile - Siri Shortcuts Integration
 *
 * Enables Siri voice commands for common DexAI actions:
 * - "Hey Siri, what's my next task?"
 * - "Hey Siri, I'm starting a task"
 * - "Hey Siri, snooze my reminders"
 *
 * Also donates user activities for Siri Suggestions.
 *
 * Note: Requires expo-siri-shortcuts or react-native-siri-shortcut.
 * If not available, methods gracefully degrade.
 */

import { buildApiUrl, debugLog, debugError } from '../../utils/config';

// =============================================================================
// Types
// =============================================================================

/**
 * Siri shortcut identifiers
 */
export type ShortcutId =
  | 'next_task' // What's my next task?
  | 'start_task' // I'm starting a task
  | 'complete_step' // I finished a step
  | 'snooze_reminders' // Snooze my reminders
  | 'start_focus' // Start focus mode
  | 'end_focus' // End focus mode
  | 'check_in' // Quick check-in
  | 'add_task'; // Add a task

/**
 * Shortcut definition
 */
export interface ShortcutDefinition {
  /** Unique identifier */
  id: ShortcutId;
  /** Display title */
  title: string;
  /** Suggested invocation phrase */
  suggestedPhrase: string;
  /** Description for settings */
  description: string;
  /** Whether shortcut is enabled */
  enabled: boolean;
  /** Icon SF Symbol name (iOS) */
  iconName: string;
}

/**
 * Shortcut invocation result
 */
export interface ShortcutResult {
  /** Whether shortcut succeeded */
  success: boolean;
  /** Response to speak back */
  spokenResponse: string;
  /** Additional data */
  data?: Record<string, unknown>;
  /** Should continue in app */
  continueInApp?: boolean;
}

/**
 * User activity for Siri Suggestions
 */
export interface UserActivity {
  /** Activity type */
  type: string;
  /** Activity title */
  title: string;
  /** Keywords for search */
  keywords: string[];
  /** User info payload */
  userInfo: Record<string, unknown>;
  /** Web page URL (for continuity) */
  webpageURL?: string;
  /** Should index for spotlight */
  isEligibleForSearch: boolean;
  /** Should show in Siri suggestions */
  isEligibleForPrediction: boolean;
}

// =============================================================================
// Module State
// =============================================================================

let siriShortcuts: any = null;
let isModuleAvailable = false;

// Registered shortcuts
const registeredShortcuts: Map<ShortcutId, ShortcutDefinition> = new Map();

// Shortcut handler
type ShortcutHandler = (shortcutId: ShortcutId, params?: any) => Promise<ShortcutResult>;
let shortcutHandler: ShortcutHandler | null = null;

// =============================================================================
// Default Shortcuts
// =============================================================================

export const DEFAULT_SHORTCUTS: ShortcutDefinition[] = [
  {
    id: 'next_task',
    title: 'Next Task',
    suggestedPhrase: "What's my next task?",
    description: 'Ask Dex what to work on next',
    enabled: true,
    iconName: 'checklist',
  },
  {
    id: 'start_task',
    title: 'Start Task',
    suggestedPhrase: "I'm starting a task",
    description: 'Tell Dex you are starting your next task',
    enabled: true,
    iconName: 'play.fill',
  },
  {
    id: 'complete_step',
    title: 'Complete Step',
    suggestedPhrase: 'I finished a step',
    description: 'Mark the current step as done',
    enabled: true,
    iconName: 'checkmark.circle.fill',
  },
  {
    id: 'snooze_reminders',
    title: 'Snooze Reminders',
    suggestedPhrase: 'Snooze my reminders',
    description: 'Snooze all reminders for 30 minutes',
    enabled: true,
    iconName: 'bell.slash',
  },
  {
    id: 'start_focus',
    title: 'Start Focus',
    suggestedPhrase: 'Start focus mode',
    description: 'Enter focus mode with DND',
    enabled: true,
    iconName: 'scope',
  },
  {
    id: 'end_focus',
    title: 'End Focus',
    suggestedPhrase: 'End focus mode',
    description: 'Exit focus mode',
    enabled: true,
    iconName: 'hand.raised',
  },
  {
    id: 'check_in',
    title: 'Check In',
    suggestedPhrase: 'Check in with Dex',
    description: 'Quick status check and guidance',
    enabled: true,
    iconName: 'person.wave.2',
  },
  {
    id: 'add_task',
    title: 'Add Task',
    suggestedPhrase: 'Add a task',
    description: 'Quickly add a new task',
    enabled: true,
    iconName: 'plus.circle.fill',
  },
];

// =============================================================================
// Initialization
// =============================================================================

/**
 * Initialize Siri shortcuts
 */
export const initializeSiriShortcuts = async (): Promise<boolean> => {
  try {
    // Try to import the native module
    siriShortcuts = await import('expo-siri-shortcuts').catch(() => null);

    if (!siriShortcuts) {
      // Try alternative module
      siriShortcuts = await import('react-native-siri-shortcut').catch(() => null);
    }

    if (!siriShortcuts) {
      debugLog('Siri: Module not available');
      isModuleAvailable = false;
      return false;
    }

    isModuleAvailable = true;

    // Register default shortcuts
    for (const shortcut of DEFAULT_SHORTCUTS) {
      if (shortcut.enabled) {
        await registerShortcut(shortcut);
      }
    }

    // Set up listener for shortcut invocations
    if (siriShortcuts.addShortcutListener) {
      siriShortcuts.addShortcutListener(handleShortcutInvocation);
    }

    debugLog('Siri: Initialized with', registeredShortcuts.size, 'shortcuts');
    return true;
  } catch (error) {
    debugError('Siri: Initialization failed', error);
    isModuleAvailable = false;
    return false;
  }
};

/**
 * Check if Siri shortcuts are available
 */
export const isSiriAvailable = (): boolean => {
  return isModuleAvailable;
};

// =============================================================================
// Shortcut Registration
// =============================================================================

/**
 * Register a Siri shortcut
 */
export const registerShortcut = async (shortcut: ShortcutDefinition): Promise<boolean> => {
  if (!isModuleAvailable) {
    registeredShortcuts.set(shortcut.id, shortcut);
    return false;
  }

  try {
    if (siriShortcuts.donateShortcut) {
      await siriShortcuts.donateShortcut({
        activityType: `app.dexai.shortcut.${shortcut.id}`,
        title: shortcut.title,
        suggestedInvocationPhrase: shortcut.suggestedPhrase,
        isEligibleForSearch: true,
        isEligibleForPrediction: true,
        userInfo: { shortcutId: shortcut.id },
      });
    }

    registeredShortcuts.set(shortcut.id, shortcut);
    debugLog('Siri: Registered shortcut', shortcut.id);
    return true;
  } catch (error) {
    debugError('Siri: Failed to register shortcut', shortcut.id, error);
    return false;
  }
};

/**
 * Unregister a Siri shortcut
 */
export const unregisterShortcut = async (shortcutId: ShortcutId): Promise<boolean> => {
  if (!isModuleAvailable) {
    registeredShortcuts.delete(shortcutId);
    return true;
  }

  try {
    if (siriShortcuts.clearShortcut) {
      await siriShortcuts.clearShortcut(`app.dexai.shortcut.${shortcutId}`);
    }

    registeredShortcuts.delete(shortcutId);
    debugLog('Siri: Unregistered shortcut', shortcutId);
    return true;
  } catch (error) {
    debugError('Siri: Failed to unregister shortcut', shortcutId, error);
    return false;
  }
};

/**
 * Get all registered shortcuts
 */
export const getRegisteredShortcuts = (): ShortcutDefinition[] => {
  return Array.from(registeredShortcuts.values());
};

// =============================================================================
// Shortcut Handler
// =============================================================================

/**
 * Set custom shortcut handler
 */
export const setShortcutHandler = (handler: ShortcutHandler): void => {
  shortcutHandler = handler;
};

/**
 * Handle shortcut invocation
 */
const handleShortcutInvocation = async (data: { activityType: string; userInfo: any }): Promise<void> => {
  const shortcutId = data.userInfo?.shortcutId as ShortcutId;

  if (!shortcutId) {
    debugError('Siri: Invalid shortcut invocation', data);
    return;
  }

  debugLog('Siri: Shortcut invoked', shortcutId);

  const handler = shortcutHandler || defaultShortcutHandler;
  const result = await handler(shortcutId, data.userInfo);

  // Provide spoken response if available
  if (result.spokenResponse && siriShortcuts.presentShortcut) {
    siriShortcuts.presentShortcut({
      response: result.spokenResponse,
    });
  }
};

/**
 * Default shortcut handler that calls backend
 */
const defaultShortcutHandler = async (
  shortcutId: ShortcutId,
  params?: any
): Promise<ShortcutResult> => {
  try {
    const response = await fetch(buildApiUrl(`/api/mobile/shortcut/${shortcutId}`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ params }),
    });

    if (!response.ok) {
      throw new Error(`Server returned ${response.status}`);
    }

    const result = await response.json();

    return {
      success: result.success,
      spokenResponse: result.spoken_response || getDefaultResponse(shortcutId, result.success),
      data: result.data,
      continueInApp: result.continue_in_app,
    };
  } catch (error) {
    debugError('Siri: Shortcut handler failed', error);
    return {
      success: false,
      spokenResponse: "Sorry, I couldn't complete that action right now.",
    };
  }
};

/**
 * Get default spoken response for shortcut
 */
const getDefaultResponse = (shortcutId: ShortcutId, success: boolean): string => {
  if (!success) {
    return "Sorry, something went wrong.";
  }

  switch (shortcutId) {
    case 'next_task':
      return "Here's what you should focus on next.";
    case 'start_task':
      return "Great! You've started the task.";
    case 'complete_step':
      return "Nice work! Step marked as done.";
    case 'snooze_reminders':
      return "Reminders snoozed for 30 minutes.";
    case 'start_focus':
      return "Focus mode activated. Good luck!";
    case 'end_focus':
      return "Focus mode ended. Nice session!";
    case 'check_in':
      return "Here's your current status.";
    case 'add_task':
      return "Task added successfully.";
    default:
      return "Done!";
  }
};

// =============================================================================
// Activity Donation (Siri Suggestions)
// =============================================================================

/**
 * Donate user activity for Siri Suggestions
 *
 * Call this when user performs actions that could be suggested.
 */
export const donateActivity = async (activity: UserActivity): Promise<boolean> => {
  if (!isModuleAvailable) {
    debugLog('Siri: Cannot donate activity - module not available');
    return false;
  }

  try {
    if (siriShortcuts.donateShortcut) {
      await siriShortcuts.donateShortcut({
        activityType: activity.type,
        title: activity.title,
        keywords: activity.keywords,
        userInfo: activity.userInfo,
        webpageURL: activity.webpageURL,
        isEligibleForSearch: activity.isEligibleForSearch,
        isEligibleForPrediction: activity.isEligibleForPrediction,
      });
    }

    debugLog('Siri: Donated activity', activity.type);
    return true;
  } catch (error) {
    debugError('Siri: Failed to donate activity', error);
    return false;
  }
};

/**
 * Donate task view activity
 */
export const donateTaskViewActivity = async (
  taskId: string,
  taskTitle: string
): Promise<boolean> => {
  return donateActivity({
    type: `app.dexai.task.${taskId}`,
    title: `View: ${taskTitle}`,
    keywords: ['task', 'view', taskTitle],
    userInfo: { taskId, action: 'view' },
    isEligibleForSearch: true,
    isEligibleForPrediction: true,
  });
};

/**
 * Donate task completion activity
 */
export const donateTaskCompletionActivity = async (
  taskId: string,
  taskTitle: string
): Promise<boolean> => {
  return donateActivity({
    type: 'app.dexai.task.complete',
    title: `Completed: ${taskTitle}`,
    keywords: ['task', 'complete', 'done', taskTitle],
    userInfo: { taskId, action: 'complete' },
    isEligibleForSearch: false,
    isEligibleForPrediction: true,
  });
};

// =============================================================================
// Present Add to Siri
// =============================================================================

/**
 * Present the "Add to Siri" UI for a shortcut
 */
export const presentAddToSiri = async (shortcutId: ShortcutId): Promise<boolean> => {
  const shortcut = registeredShortcuts.get(shortcutId);

  if (!shortcut) {
    debugError('Siri: Shortcut not found', shortcutId);
    return false;
  }

  if (!isModuleAvailable || !siriShortcuts.presentShortcut) {
    debugLog('Siri: Cannot present Add to Siri UI');
    return false;
  }

  try {
    await siriShortcuts.presentShortcut({
      activityType: `app.dexai.shortcut.${shortcutId}`,
      title: shortcut.title,
      suggestedInvocationPhrase: shortcut.suggestedPhrase,
      userInfo: { shortcutId },
    });

    return true;
  } catch (error) {
    debugError('Siri: Failed to present Add to Siri', error);
    return false;
  }
};

// =============================================================================
// Cleanup
// =============================================================================

/**
 * Clean up Siri shortcuts
 */
export const cleanupSiriShortcuts = (): void => {
  if (siriShortcuts?.removeShortcutListener) {
    siriShortcuts.removeShortcutListener(handleShortcutInvocation);
  }

  shortcutHandler = null;
  debugLog('Siri: Cleaned up');
};

// =============================================================================
// Exports
// =============================================================================

export default {
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
};
