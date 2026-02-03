/**
 * DexAI Mobile - Main App Entry Point
 *
 * This is an Expo wrapper around the DexAI PWA dashboard that provides:
 * - Native push notifications for iOS and Android
 * - Background fetch for syncing
 * - Deep linking support
 * - Native app shell experience
 * - Home screen widgets
 * - Apple Watch support
 * - Siri Shortcuts
 * - 3D Touch quick actions
 *
 * Architecture:
 * - The app primarily displays the PWA dashboard in a WebView
 * - Native features (push, background) are handled by Expo modules
 * - The JS bridge allows communication between native and web
 */

import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  StyleSheet,
  View,
  StatusBar,
  AppState,
  AppStateStatus,
  Platform,
  Linking,
} from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import * as SplashScreen from 'expo-splash-screen';
import * as Notifications from 'expo-notifications';

// Components
import WebViewContainer, {
  WebViewContainerRef,
} from './src/components/WebViewContainer';

// Services
import {
  registerForPushNotificationsAsync,
  setupNotificationListeners,
  isDeviceSupported,
} from './src/services/push';
import {
  registerBackgroundFetch,
  registerBackgroundNotifications,
  cleanupBackgroundTasks,
} from './src/services/background';

// Native Features (Phase 10c)
import {
  initializeWatchConnectivity,
  sendFullSync as syncWatch,
  cleanupWatchConnectivity,
} from './src/native/watch';
import {
  initializeSiriShortcuts,
  cleanupSiriShortcuts,
  donateTaskViewActivity,
} from './src/native/shortcuts';
import {
  initializeQuickActions,
  getPendingAction,
  refreshDynamicActions,
  cleanupQuickActions,
} from './src/native/shortcuts';
import {
  initializeBackgroundSync,
  cleanupBackgroundSync,
} from './src/native/sync';
import { loadQueue } from './src/native/sync';

// Utils
import { config, debugLog, debugError, buildDashboardUrl } from './src/utils/config';
import { navigateWebView } from './src/utils/bridge';
import { AppState as DexAppState, NotificationData } from './src/types';

// Keep splash screen visible while initializing
SplashScreen.preventAutoHideAsync();

// =============================================================================
// App Component
// =============================================================================

export default function App() {
  // Refs
  const webViewRef = useRef<WebViewContainerRef>(null);
  const appStateRef = useRef<AppStateStatus>(AppState.currentState);

  // State
  const [isInitialized, setIsInitialized] = useState(false);
  const [appState, setAppState] = useState<DexAppState>({
    initialized: false,
    pushToken: null,
    webViewReady: false,
    userId: null,
    isAuthenticated: false,
    badgeCount: 0,
    isOnline: true,
    isActive: true,
  });

  // ============================================================================
  // Initialization
  // ============================================================================

  /**
   * Initialize app on mount
   */
  useEffect(() => {
    const initialize = async () => {
      debugLog('App: Initializing...');

      try {
        // Set up notification listeners
        const cleanupNotifications = setupNotificationListeners();

        // Register background tasks
        await registerBackgroundFetch();
        await registerBackgroundNotifications();

        // Get a default user ID (in real app, this comes from auth)
        // For now, use device-based ID
        const userId = 'default';

        // Register for push notifications
        if (isDeviceSupported()) {
          const token = await registerForPushNotificationsAsync(userId);
          if (token) {
            setAppState((prev) => ({ ...prev, pushToken: token }));
          }
        } else {
          debugLog('App: Push notifications not supported on this device');
        }

        // =================================================================
        // Initialize Native Features (Phase 10c)
        // =================================================================

        // Load offline queue from storage
        await loadQueue();
        debugLog('App: Offline queue loaded');

        // Initialize enhanced background sync
        await initializeBackgroundSync();
        debugLog('App: Background sync initialized');

        // Initialize Siri Shortcuts (iOS only, fails gracefully on Android)
        if (Platform.OS === 'ios') {
          await initializeSiriShortcuts();
          debugLog('App: Siri Shortcuts initialized');
        }

        // Initialize Quick Actions (3D Touch / Long Press)
        await initializeQuickActions();
        debugLog('App: Quick Actions initialized');

        // Check for pending quick action (app launched via quick action)
        const pendingAction = getPendingAction();
        if (pendingAction) {
          debugLog('App: Pending quick action found', pendingAction.id);
          // Handle after WebView is ready
        }

        // Initialize Apple Watch connectivity (iOS only)
        if (Platform.OS === 'ios') {
          await initializeWatchConnectivity();
          debugLog('App: Watch connectivity initialized');
        }

        // Refresh dynamic quick actions based on server data
        await refreshDynamicActions();

        // Update state
        setAppState((prev) => ({
          ...prev,
          initialized: true,
          userId,
        }));

        setIsInitialized(true);
        debugLog('App: Initialization complete');

        // Hide splash screen
        await SplashScreen.hideAsync();

        // Return cleanup function
        return () => {
          cleanupNotifications();
        };
      } catch (error) {
        debugError('App: Initialization failed', error);
        setIsInitialized(true);
        await SplashScreen.hideAsync();
      }
    };

    initialize();
  }, []);

  // ============================================================================
  // App State Handling
  // ============================================================================

  /**
   * Handle app state changes (foreground/background)
   */
  useEffect(() => {
    const handleAppStateChange = async (nextAppState: AppStateStatus) => {
      const wasBackground =
        appStateRef.current.match(/inactive|background/) !== null;
      const isNowForeground = nextAppState === 'active';

      debugLog('App: State change', {
        from: appStateRef.current,
        to: nextAppState,
      });

      // App came to foreground
      if (wasBackground && isNowForeground) {
        debugLog('App: Returned to foreground');
        setAppState((prev) => ({ ...prev, isActive: true }));

        // Clear badge when app opens
        Notifications.setBadgeCountAsync(0);

        // Refresh WebView if needed
        // webViewRef.current?.reload();
      }

      // App went to background
      if (!isNowForeground && appStateRef.current === 'active') {
        debugLog('App: Went to background');
        setAppState((prev) => ({ ...prev, isActive: false }));
      }

      appStateRef.current = nextAppState;
    };

    const subscription = AppState.addEventListener('change', handleAppStateChange);

    return () => {
      subscription.remove();
    };
  }, []);

  // ============================================================================
  // Deep Linking
  // ============================================================================

  /**
   * Handle deep links
   */
  useEffect(() => {
    const handleDeepLink = (event: { url: string }) => {
      const { url } = event;
      debugLog('App: Deep link received', url);

      // Parse the URL and navigate in WebView
      try {
        const parsedUrl = new URL(url);

        // Handle dexai:// scheme
        if (parsedUrl.protocol === 'dexai:') {
          const path = parsedUrl.pathname;
          navigateWebView({ path });
        }
      } catch (error) {
        debugError('App: Invalid deep link URL', error);
      }
    };

    // Handle initial URL (app opened via deep link)
    Linking.getInitialURL().then((url) => {
      if (url) {
        handleDeepLink({ url });
      }
    });

    // Handle deep links when app is running
    const subscription = Linking.addEventListener('url', handleDeepLink);

    return () => {
      subscription.remove();
    };
  }, []);

  // ============================================================================
  // Notification Response Handling
  // ============================================================================

  /**
   * Handle notification taps that should navigate
   */
  useEffect(() => {
    // Get the notification that opened the app (if any)
    Notifications.getLastNotificationResponseAsync().then((response) => {
      if (response) {
        const data = response.notification.request.content.data as NotificationData;
        if (data?.actionUrl) {
          debugLog('App: Opened via notification', data.actionUrl);
          // Wait for WebView to be ready
          setTimeout(() => {
            navigateWebView({ path: data.actionUrl! });
          }, 1000);
        }
      }
    });

    // Listen for notification responses while app is running
    const subscription = Notifications.addNotificationResponseReceivedListener(
      (response) => {
        const data = response.notification.request.content.data as NotificationData;
        if (data?.actionUrl && appState.webViewReady) {
          navigateWebView({ path: data.actionUrl });
        }
      }
    );

    return () => {
      subscription.remove();
    };
  }, [appState.webViewReady]);

  // ============================================================================
  // Callbacks
  // ============================================================================

  /**
   * Handle WebView ready
   */
  const handleWebViewReady = useCallback(async () => {
    debugLog('App: WebView ready');
    setAppState((prev) => ({ ...prev, webViewReady: true }));

    // Handle pending quick action if any
    const pendingAction = getPendingAction();
    if (pendingAction) {
      debugLog('App: Processing pending quick action', pendingAction.id);
      // Navigate based on action
      if (pendingAction.id === 'next_task') {
        navigateWebView({ path: '/tasks/current' });
      } else if (pendingAction.id === 'quick_capture') {
        navigateWebView({ path: '/tasks/add' });
      } else if (pendingAction.id === 'focus_mode') {
        navigateWebView({ path: '/focus' });
      }
    }

    // Sync Watch with current state (iOS)
    if (Platform.OS === 'ios') {
      await syncWatch();
    }
  }, []);

  /**
   * Handle WebView navigation change
   */
  const handleNavigationChange = useCallback((url: string) => {
    debugLog('App: Navigation changed', url);
  }, []);

  /**
   * Handle WebView error
   */
  const handleWebViewError = useCallback((error: string) => {
    debugError('App: WebView error', error);
  }, []);

  // ============================================================================
  // Render
  // ============================================================================

  // Show nothing while initializing (splash screen is visible)
  if (!isInitialized) {
    return null;
  }

  return (
    <SafeAreaProvider>
      <StatusBar
        barStyle="dark-content"
        backgroundColor="#F9FAFB"
        translucent={Platform.OS === 'android'}
      />
      <SafeAreaView style={styles.container} edges={['left', 'right']}>
        <WebViewContainer
          ref={webViewRef}
          initialPath="/"
          userId={appState.userId ?? undefined}
          onReady={handleWebViewReady}
          onNavigationChange={handleNavigationChange}
          onError={handleWebViewError}
        />
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

// =============================================================================
// Styles
// =============================================================================

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F9FAFB',
  },
});
