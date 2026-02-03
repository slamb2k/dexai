/**
 * DexAI Mobile - Next Task Widget
 *
 * Home screen widget showing the user's next task and current step.
 * ADHD-friendly: Single focus, no overwhelm.
 *
 * Features:
 * - Shows current task title
 * - Shows current step (one thing at a time)
 * - Energy level indicator
 * - Upcoming task count badge
 * - Tap to open app at task
 *
 * Note: This component is designed for expo-widgets but can also be
 * rendered as a preview in the app. The actual widget rendering happens
 * in native code via the widget extension.
 */

import React, { useEffect, useState, useCallback } from 'react';
import {
  StyleSheet,
  View,
  Text,
  TouchableOpacity,
  Linking,
  ActivityIndicator,
} from 'react-native';
import { buildApiUrl, debugLog, debugError } from '../../utils/config';
import {
  DEFAULT_DISPLAY_OPTIONS,
  WIDGET_THEMES,
  getEnergyColor,
  WidgetDisplayOptions,
} from './config';

// =============================================================================
// Types
// =============================================================================

export interface WidgetData {
  /** Current task title */
  taskTitle: string | null;
  /** Current step description */
  currentStep: string | null;
  /** Step number (e.g., 2 of 5) */
  stepNumber: number | null;
  /** Total steps */
  totalSteps: number | null;
  /** Task ID for deep linking */
  taskId: string | null;
  /** Energy level */
  energyLevel: 'high' | 'medium' | 'low' | 'unknown';
  /** Number of upcoming tasks */
  upcomingCount: number;
  /** Last update timestamp */
  lastUpdated: string;
  /** Error message if any */
  error?: string;
}

interface NextTaskWidgetProps {
  /** User ID for fetching data */
  userId?: string;
  /** Display options */
  displayOptions?: Partial<WidgetDisplayOptions>;
  /** Use dark theme */
  darkMode?: boolean;
  /** Callback when widget data updates */
  onDataUpdate?: (data: WidgetData) => void;
  /** Callback when widget is tapped */
  onPress?: () => void;
}

// =============================================================================
// Default Data
// =============================================================================

const DEFAULT_WIDGET_DATA: WidgetData = {
  taskTitle: null,
  currentStep: null,
  stepNumber: null,
  totalSteps: null,
  taskId: null,
  energyLevel: 'unknown',
  upcomingCount: 0,
  lastUpdated: new Date().toISOString(),
};

// =============================================================================
// Component
// =============================================================================

export const NextTaskWidget: React.FC<NextTaskWidgetProps> = ({
  userId = 'default',
  displayOptions = {},
  darkMode = false,
  onDataUpdate,
  onPress,
}) => {
  const [data, setData] = useState<WidgetData>(DEFAULT_WIDGET_DATA);
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);

  const options = { ...DEFAULT_DISPLAY_OPTIONS, ...displayOptions };
  const theme = darkMode ? WIDGET_THEMES.dark : WIDGET_THEMES.light;

  // ===========================================================================
  // Data Fetching
  // ===========================================================================

  const fetchWidgetData = useCallback(async () => {
    try {
      setIsLoading(true);
      setHasError(false);

      const response = await fetch(
        buildApiUrl(`/api/mobile/widget-data?user_id=${userId}`),
        {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) {
        throw new Error(`Server returned ${response.status}`);
      }

      const result = await response.json();

      const newData: WidgetData = {
        taskTitle: result.next_task?.title || null,
        currentStep: result.current_step?.description || null,
        stepNumber: result.current_step?.step_number || null,
        totalSteps: result.current_step?.total_steps || null,
        taskId: result.next_task?.id || null,
        energyLevel: result.energy_level || 'unknown',
        upcomingCount: result.upcoming_count || 0,
        lastUpdated: new Date().toISOString(),
      };

      setData(newData);
      onDataUpdate?.(newData);

      debugLog('Widget data fetched', newData);
    } catch (error) {
      debugError('Widget data fetch failed', error);
      setHasError(true);
      setData({
        ...DEFAULT_WIDGET_DATA,
        error: error instanceof Error ? error.message : 'Failed to load',
        lastUpdated: new Date().toISOString(),
      });
    } finally {
      setIsLoading(false);
    }
  }, [userId, onDataUpdate]);

  useEffect(() => {
    fetchWidgetData();
  }, [fetchWidgetData]);

  // ===========================================================================
  // Handlers
  // ===========================================================================

  const handlePress = useCallback(() => {
    if (onPress) {
      onPress();
      return;
    }

    // Default: open app with deep link to task
    if (data.taskId) {
      Linking.openURL(`dexai://task/${data.taskId}`);
    } else {
      Linking.openURL('dexai://');
    }
  }, [onPress, data.taskId]);

  // ===========================================================================
  // Render Helpers
  // ===========================================================================

  const truncateText = (text: string, maxLength: number): string => {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength - 3) + '...';
  };

  const renderEnergyIndicator = () => {
    if (!options.showEnergy) return null;

    const color = getEnergyColor(data.energyLevel);

    return (
      <View style={[styles.energyIndicator, { backgroundColor: color }]} />
    );
  };

  const renderStepProgress = () => {
    if (!options.showStepProgress || !data.stepNumber || !data.totalSteps) {
      return null;
    }

    return (
      <Text style={[styles.stepProgress, { color: theme.textSecondary }]}>
        Step {data.stepNumber} of {data.totalSteps}
      </Text>
    );
  };

  const renderUpcomingBadge = () => {
    if (!options.showUpcomingCount || data.upcomingCount <= 0) {
      return null;
    }

    return (
      <View style={[styles.badge, { backgroundColor: theme.accent }]}>
        <Text style={styles.badgeText}>
          +{data.upcomingCount > 99 ? '99' : data.upcomingCount}
        </Text>
      </View>
    );
  };

  // ===========================================================================
  // Main Render
  // ===========================================================================

  if (isLoading) {
    return (
      <View style={[styles.container, { backgroundColor: theme.background }]}>
        <ActivityIndicator size="small" color={theme.accent} />
      </View>
    );
  }

  if (hasError) {
    return (
      <TouchableOpacity
        style={[styles.container, { backgroundColor: theme.background }]}
        onPress={fetchWidgetData}
        activeOpacity={0.7}
      >
        <Text style={[styles.errorText, { color: theme.textSecondary }]}>
          Tap to retry
        </Text>
      </TouchableOpacity>
    );
  }

  // No task state
  if (!data.taskTitle) {
    return (
      <TouchableOpacity
        style={[styles.container, { backgroundColor: theme.background }]}
        onPress={handlePress}
        activeOpacity={0.7}
      >
        <Text style={[styles.emptyTitle, { color: theme.text }]}>
          All clear!
        </Text>
        <Text style={[styles.emptySubtitle, { color: theme.textSecondary }]}>
          No tasks right now
        </Text>
        {renderUpcomingBadge()}
      </TouchableOpacity>
    );
  }

  return (
    <TouchableOpacity
      style={[
        styles.container,
        { backgroundColor: theme.background, borderColor: theme.border },
      ]}
      onPress={handlePress}
      activeOpacity={0.7}
    >
      {/* Header: Energy + Badge */}
      <View style={styles.header}>
        {renderEnergyIndicator()}
        <Text style={[styles.label, { color: theme.textSecondary }]}>
          Next Task
        </Text>
        {renderUpcomingBadge()}
      </View>

      {/* Task Title */}
      <Text
        style={[styles.taskTitle, { color: theme.text }]}
        numberOfLines={2}
      >
        {truncateText(data.taskTitle, options.maxTitleLength)}
      </Text>

      {/* Current Step */}
      {data.currentStep && (
        <View style={styles.stepContainer}>
          <Text
            style={[styles.currentStep, { color: theme.textSecondary }]}
            numberOfLines={2}
          >
            {truncateText(data.currentStep, options.maxBodyLength)}
          </Text>
          {renderStepProgress()}
        </View>
      )}
    </TouchableOpacity>
  );
};

// =============================================================================
// Styles
// =============================================================================

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 12,
    borderRadius: 16,
    borderWidth: 1,
    minWidth: 150,
    minHeight: 150,
    justifyContent: 'flex-start',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  energyIndicator: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 6,
  },
  label: {
    fontSize: 11,
    fontWeight: '500',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    flex: 1,
  },
  badge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 10,
  },
  badgeText: {
    color: '#FFFFFF',
    fontSize: 10,
    fontWeight: '600',
  },
  taskTitle: {
    fontSize: 16,
    fontWeight: '600',
    lineHeight: 20,
    marginBottom: 6,
  },
  stepContainer: {
    marginTop: 'auto',
  },
  currentStep: {
    fontSize: 13,
    lineHeight: 18,
  },
  stepProgress: {
    fontSize: 10,
    marginTop: 4,
  },
  emptyTitle: {
    fontSize: 16,
    fontWeight: '600',
    textAlign: 'center',
    marginTop: 'auto',
  },
  emptySubtitle: {
    fontSize: 13,
    textAlign: 'center',
    marginBottom: 'auto',
    marginTop: 4,
  },
  errorText: {
    fontSize: 13,
    textAlign: 'center',
  },
});

// =============================================================================
// Exports
// =============================================================================

export default NextTaskWidget;
