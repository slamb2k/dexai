/**
 * DexAI Mobile - Widget Configuration
 *
 * Configuration for home screen widgets (iOS and Android).
 * ADHD-friendly: Shows single-focus task view.
 */

// =============================================================================
// Widget Size Types
// =============================================================================

export type WidgetSize = 'small' | 'medium';

export interface WidgetConfig {
  /** Widget unique identifier */
  id: string;
  /** Human-readable name */
  name: string;
  /** Size of the widget */
  size: WidgetSize;
  /** Refresh interval in minutes */
  refreshIntervalMinutes: number;
  /** Whether the widget is enabled */
  enabled: boolean;
}

// =============================================================================
// Widget Display Options
// =============================================================================

export interface WidgetDisplayOptions {
  /** Show energy indicator */
  showEnergy: boolean;
  /** Show upcoming task count */
  showUpcomingCount: boolean;
  /** Show current step number */
  showStepProgress: boolean;
  /** Use compact layout */
  compactMode: boolean;
  /** Maximum title length before truncation */
  maxTitleLength: number;
  /** Maximum body length before truncation */
  maxBodyLength: number;
}

// =============================================================================
// Default Configuration
// =============================================================================

export const DEFAULT_WIDGET_CONFIG: WidgetConfig = {
  id: 'next_task',
  name: 'Next Task',
  size: 'small',
  refreshIntervalMinutes: 60,
  enabled: true,
};

export const DEFAULT_DISPLAY_OPTIONS: WidgetDisplayOptions = {
  showEnergy: true,
  showUpcomingCount: true,
  showStepProgress: true,
  compactMode: false,
  maxTitleLength: 40,
  maxBodyLength: 80,
};

// =============================================================================
// Widget Sizes Configuration
// =============================================================================

export interface WidgetSizeConfig {
  /** Width in grid units */
  width: number;
  /** Height in grid units */
  height: number;
  /** iOS supportedFamilies value */
  iosSupportedFamilies: string[];
  /** Android widget dimensions in dp */
  androidMinWidth: number;
  androidMinHeight: number;
}

export const WIDGET_SIZES: Record<WidgetSize, WidgetSizeConfig> = {
  small: {
    width: 2,
    height: 2,
    iosSupportedFamilies: ['systemSmall'],
    androidMinWidth: 110,
    androidMinHeight: 110,
  },
  medium: {
    width: 4,
    height: 2,
    iosSupportedFamilies: ['systemSmall', 'systemMedium'],
    androidMinWidth: 250,
    androidMinHeight: 110,
  },
};

// =============================================================================
// Refresh Configuration
// =============================================================================

export interface RefreshConfig {
  /** Minimum interval in minutes */
  minIntervalMinutes: number;
  /** Maximum interval in minutes */
  maxIntervalMinutes: number;
  /** Default interval in minutes */
  defaultIntervalMinutes: number;
  /** Available presets */
  presets: { label: string; minutes: number }[];
}

export const REFRESH_CONFIG: RefreshConfig = {
  minIntervalMinutes: 15,
  maxIntervalMinutes: 240,
  defaultIntervalMinutes: 60,
  presets: [
    { label: '15 minutes', minutes: 15 },
    { label: '30 minutes', minutes: 30 },
    { label: '1 hour', minutes: 60 },
    { label: '2 hours', minutes: 120 },
    { label: '4 hours', minutes: 240 },
  ],
};

// =============================================================================
// Widget Theme Colors
// =============================================================================

export interface WidgetTheme {
  /** Background color */
  background: string;
  /** Text color */
  text: string;
  /** Secondary text color */
  textSecondary: string;
  /** Accent color (energy indicator, etc.) */
  accent: string;
  /** Border color */
  border: string;
}

export const WIDGET_THEMES: { light: WidgetTheme; dark: WidgetTheme } = {
  light: {
    background: '#FFFFFF',
    text: '#111827',
    textSecondary: '#6B7280',
    accent: '#4F46E5',
    border: '#E5E7EB',
  },
  dark: {
    background: '#1F2937',
    text: '#F9FAFB',
    textSecondary: '#9CA3AF',
    accent: '#818CF8',
    border: '#374151',
  },
};

// =============================================================================
// Energy Level Colors
// =============================================================================

export const ENERGY_COLORS = {
  high: '#10B981', // Green
  medium: '#F59E0B', // Amber
  low: '#EF4444', // Red
  unknown: '#9CA3AF', // Gray
};

export const getEnergyColor = (
  level: 'high' | 'medium' | 'low' | 'unknown'
): string => {
  return ENERGY_COLORS[level] || ENERGY_COLORS.unknown;
};

// =============================================================================
// Exports
// =============================================================================

export default {
  DEFAULT_WIDGET_CONFIG,
  DEFAULT_DISPLAY_OPTIONS,
  WIDGET_SIZES,
  REFRESH_CONFIG,
  WIDGET_THEMES,
  ENERGY_COLORS,
  getEnergyColor,
};
