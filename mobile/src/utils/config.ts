/**
 * DexAI Mobile - App Configuration
 *
 * Centralized configuration management for the mobile app.
 * Values can be overridden via environment variables or Expo Constants.
 */

import Constants from 'expo-constants';
import { AppConfig } from '../types';

// =============================================================================
// Environment Detection
// =============================================================================

/**
 * Detect current environment based on Expo release channel or env vars
 */
const getEnvironment = (): 'development' | 'staging' | 'production' => {
  const releaseChannel = Constants.expoConfig?.extra?.releaseChannel;

  if (__DEV__) {
    return 'development';
  }

  if (releaseChannel?.includes('staging')) {
    return 'staging';
  }

  return 'production';
};

// =============================================================================
// Configuration Values
// =============================================================================

/**
 * Environment-specific API URLs
 */
const API_URLS: Record<string, string> = {
  development: 'http://localhost:8000',
  staging: 'https://staging-api.dexai.app',
  production: 'https://api.dexai.app',
};

/**
 * Environment-specific dashboard URLs
 */
const DASHBOARD_URLS: Record<string, string> = {
  development: 'http://localhost:3000',
  staging: 'https://staging.dexai.app',
  production: 'https://app.dexai.app',
};

// =============================================================================
// Config Object
// =============================================================================

const environment = getEnvironment();

/**
 * App configuration object
 *
 * Can be overridden via Expo Constants (app.json extra) or process.env
 */
export const config: AppConfig = {
  // API endpoint for backend communication
  apiUrl:
    Constants.expoConfig?.extra?.apiUrl ||
    process.env.EXPO_PUBLIC_API_URL ||
    API_URLS[environment],

  // Dashboard URL to load in WebView
  dashboardUrl:
    Constants.expoConfig?.extra?.dashboardUrl ||
    process.env.EXPO_PUBLIC_DASHBOARD_URL ||
    DASHBOARD_URLS[environment],

  // Enable debug logging
  debug:
    Constants.expoConfig?.extra?.debug ??
    process.env.EXPO_PUBLIC_DEBUG === 'true' ??
    environment === 'development',

  // Background fetch interval in seconds (minimum 15 minutes on iOS)
  backgroundFetchInterval:
    Constants.expoConfig?.extra?.backgroundFetchInterval ??
    parseInt(process.env.EXPO_PUBLIC_BG_FETCH_INTERVAL || '900', 10),

  // Maximum badge count to display (iOS shows 99+, Android varies)
  maxBadgeCount:
    Constants.expoConfig?.extra?.maxBadgeCount ??
    parseInt(process.env.EXPO_PUBLIC_MAX_BADGE || '99', 10),
};

// =============================================================================
// Feature Flags
// =============================================================================

/**
 * Feature flags for gradual rollout and A/B testing
 */
export const featureFlags = {
  // Enable background sync functionality
  backgroundSyncEnabled:
    Constants.expoConfig?.extra?.features?.backgroundSync ?? true,

  // Enable native notifications (vs. WebView-only)
  nativeNotificationsEnabled:
    Constants.expoConfig?.extra?.features?.nativeNotifications ?? true,

  // Enable deep linking
  deepLinkingEnabled:
    Constants.expoConfig?.extra?.features?.deepLinking ?? true,

  // Enable biometric authentication
  biometricAuthEnabled:
    Constants.expoConfig?.extra?.features?.biometricAuth ?? false,

  // Enable offline mode caching
  offlineModeEnabled:
    Constants.expoConfig?.extra?.features?.offlineMode ?? false,

  // Enable haptic feedback
  hapticFeedbackEnabled:
    Constants.expoConfig?.extra?.features?.hapticFeedback ?? true,
};

// =============================================================================
// URL Helpers
// =============================================================================

/**
 * Build API endpoint URL
 */
export const buildApiUrl = (path: string): string => {
  const baseUrl = config.apiUrl.replace(/\/$/, '');
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${baseUrl}${cleanPath}`;
};

/**
 * Build dashboard URL with optional path
 */
export const buildDashboardUrl = (path = '/'): string => {
  const baseUrl = config.dashboardUrl.replace(/\/$/, '');
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${baseUrl}${cleanPath}`;
};

// =============================================================================
// Debug Logging
// =============================================================================

/**
 * Log message if debug mode is enabled
 */
export const debugLog = (message: string, data?: unknown): void => {
  if (config.debug) {
    console.log(`[DexAI] ${message}`, data ?? '');
  }
};

/**
 * Log error if debug mode is enabled
 */
export const debugError = (message: string, error?: unknown): void => {
  if (config.debug) {
    console.error(`[DexAI] ${message}`, error ?? '');
  }
};

// =============================================================================
// Exports
// =============================================================================

export default config;
