/**
 * DexAI Mobile - WebView Container Component
 *
 * Wraps the PWA dashboard in a WebView with:
 * - Auth token injection
 * - JS bridge for native <-> web communication
 * - Pull-to-refresh support
 * - Loading indicator
 * - Error handling with retry
 * - Offline detection
 */

import React, {
  useRef,
  useState,
  useCallback,
  useEffect,
  forwardRef,
  useImperativeHandle,
} from 'react';
import {
  View,
  StyleSheet,
  ActivityIndicator,
  Text,
  TouchableOpacity,
  RefreshControl,
  ScrollView,
  Platform,
  Linking,
} from 'react-native';
import { WebView, WebViewMessageEvent, WebViewNavigation } from 'react-native-webview';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as Device from 'expo-device';
import Constants from 'expo-constants';
import bridge, { getInjectedJavaScript, sendDeviceInfo } from '../utils/bridge';
import { config, buildDashboardUrl, debugLog, debugError } from '../utils/config';
import { getPermissionStatus } from '../services/push';
import { DeviceInfoPayload, NavigationPayload } from '../types';

// =============================================================================
// Types
// =============================================================================

export interface WebViewContainerProps {
  /** Initial path to load (default: '/') */
  initialPath?: string;
  /** Auth token to inject */
  authToken?: string;
  /** User ID for auth */
  userId?: string;
  /** Called when WebView navigation changes */
  onNavigationChange?: (url: string) => void;
  /** Called when WebView is ready */
  onReady?: () => void;
  /** Called on WebView error */
  onError?: (error: string) => void;
}

export interface WebViewContainerRef {
  /** Navigate to a path */
  navigateTo: (path: string) => void;
  /** Reload the WebView */
  reload: () => void;
  /** Go back in history */
  goBack: () => void;
  /** Check if can go back */
  canGoBack: () => boolean;
  /** Inject JavaScript */
  injectJS: (script: string) => void;
}

// =============================================================================
// Component
// =============================================================================

const WebViewContainer = forwardRef<WebViewContainerRef, WebViewContainerProps>(
  (
    {
      initialPath = '/',
      authToken,
      userId,
      onNavigationChange,
      onReady,
      onError,
    },
    ref
  ) => {
    const insets = useSafeAreaInsets();
    const webViewRef = useRef<WebView>(null);

    // State
    const [isLoading, setIsLoading] = useState(true);
    const [hasError, setHasError] = useState(false);
    const [errorMessage, setErrorMessage] = useState('');
    const [canGoBack, setCanGoBack] = useState(false);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [currentUrl, setCurrentUrl] = useState(buildDashboardUrl(initialPath));

    // Set up bridge with WebView ref
    useEffect(() => {
      bridge.setWebViewRef(webViewRef as React.RefObject<WebView>);

      return () => {
        bridge.reset();
      };
    }, []);

    // Expose methods via ref
    useImperativeHandle(ref, () => ({
      navigateTo: (path: string) => {
        const url = buildDashboardUrl(path);
        webViewRef.current?.injectJavaScript(`
          window.location.href = '${url}';
          true;
        `);
      },
      reload: () => {
        webViewRef.current?.reload();
      },
      goBack: () => {
        webViewRef.current?.goBack();
      },
      canGoBack: () => canGoBack,
      injectJS: (script: string) => {
        webViewRef.current?.injectJavaScript(script);
      },
    }));

    /**
     * Send device info to WebView
     */
    const sendDeviceInfoToWeb = useCallback(async () => {
      const pushPermission = await getPermissionStatus();

      const deviceInfo: DeviceInfoPayload = {
        platform: Platform.OS as 'ios' | 'android',
        osVersion: Platform.Version?.toString() ?? 'unknown',
        model: Device.modelName ?? 'unknown',
        appVersion: Constants.expoConfig?.version ?? '1.0.0',
        isTablet: Device.deviceType === Device.DeviceType.TABLET,
        deviceId: Constants.installationId ?? 'unknown',
        pushPermission,
      };

      sendDeviceInfo(deviceInfo);
    }, []);

    /**
     * Handle messages from WebView
     */
    const handleMessage = useCallback(
      (event: WebViewMessageEvent) => {
        const data = event.nativeEvent.data;
        bridge.handleMessage(data);

        try {
          const message = JSON.parse(data);

          // Handle READY message
          if (message.command === 'READY') {
            debugLog('WebView: Ready');
            bridge.setReady(true);
            sendDeviceInfoToWeb();
            onReady?.();
          }

          // Handle navigation requests from web
          if (message.command === 'NAVIGATE_NATIVE') {
            const payload = message.payload as NavigationPayload;
            debugLog('WebView: Navigate request', payload);
            // Could be used to open native screens or external links
            if (payload.path.startsWith('http')) {
              Linking.openURL(payload.path);
            }
          }

          // Handle log messages
          if (message.command === 'LOG' && config.debug) {
            const { level, args } = message.payload;
            console[level as 'log' | 'warn' | 'error']('[WebView]', ...args);
          }
        } catch {
          // Not a JSON message, ignore
        }
      },
      [sendDeviceInfoToWeb, onReady]
    );

    /**
     * Handle navigation state change
     */
    const handleNavigationChange = useCallback(
      (navState: WebViewNavigation) => {
        setCanGoBack(navState.canGoBack);
        setCurrentUrl(navState.url);
        onNavigationChange?.(navState.url);
      },
      [onNavigationChange]
    );

    /**
     * Handle load start
     */
    const handleLoadStart = useCallback(() => {
      setIsLoading(true);
      setHasError(false);
    }, []);

    /**
     * Handle load end
     */
    const handleLoadEnd = useCallback(() => {
      setIsLoading(false);
      setIsRefreshing(false);
    }, []);

    /**
     * Handle WebView error
     */
    const handleError = useCallback(
      (syntheticEvent: { nativeEvent: { description: string } }) => {
        const { description } = syntheticEvent.nativeEvent;
        debugError('WebView: Error', description);
        setHasError(true);
        setErrorMessage(description);
        setIsLoading(false);
        setIsRefreshing(false);
        onError?.(description);
      },
      [onError]
    );

    /**
     * Handle HTTP error (4xx, 5xx)
     */
    const handleHttpError = useCallback(
      (syntheticEvent: { nativeEvent: { statusCode: number } }) => {
        const { statusCode } = syntheticEvent.nativeEvent;
        debugError('WebView: HTTP error', statusCode);
        if (statusCode >= 500) {
          setHasError(true);
          setErrorMessage(`Server error (${statusCode})`);
          onError?.(`Server error: ${statusCode}`);
        }
      },
      [onError]
    );

    /**
     * Handle pull-to-refresh
     */
    const handleRefresh = useCallback(() => {
      setIsRefreshing(true);
      webViewRef.current?.reload();
    }, []);

    /**
     * Retry loading after error
     */
    const handleRetry = useCallback(() => {
      setHasError(false);
      setErrorMessage('');
      webViewRef.current?.reload();
    }, []);

    /**
     * Build injected JavaScript with auth token
     */
    const getInjectedJS = useCallback(() => {
      let script = getInjectedJavaScript();

      // Inject auth token if provided
      if (authToken && userId) {
        script += `
          window.__DEXAI_AUTH__ = {
            accessToken: '${authToken}',
            userId: '${userId}',
            timestamp: ${Date.now()}
          };

          // Also store in localStorage for the PWA
          try {
            localStorage.setItem('dexai_auth', JSON.stringify(window.__DEXAI_AUTH__));
          } catch (e) {
            console.warn('Failed to store auth in localStorage');
          }
          true;
        `;
      }

      return script;
    }, [authToken, userId]);

    /**
     * Handle URL requests - allow navigation within dashboard, open external in browser
     */
    const handleShouldStartLoad = useCallback(
      (event: WebViewNavigation) => {
        const { url } = event;

        // Allow dashboard URLs
        if (url.startsWith(config.dashboardUrl) || url.startsWith('about:')) {
          return true;
        }

        // Allow API calls
        if (url.startsWith(config.apiUrl)) {
          return true;
        }

        // Open external URLs in system browser
        debugLog('WebView: Opening external URL', url);
        Linking.openURL(url);
        return false;
      },
      []
    );

    // ==========================================================================
    // Render
    // ==========================================================================

    // Error state
    if (hasError) {
      return (
        <View style={[styles.container, styles.centerContent]}>
          <Text style={styles.errorTitle}>Unable to Load</Text>
          <Text style={styles.errorMessage}>
            {errorMessage || 'Something went wrong. Please try again.'}
          </Text>
          <TouchableOpacity style={styles.retryButton} onPress={handleRetry}>
            <Text style={styles.retryButtonText}>Try Again</Text>
          </TouchableOpacity>
        </View>
      );
    }

    return (
      <View style={[styles.container, { paddingTop: insets.top }]}>
        {/* Loading overlay */}
        {isLoading && (
          <View style={styles.loadingOverlay}>
            <ActivityIndicator size="large" color="#4F46E5" />
            <Text style={styles.loadingText}>Loading DexAI...</Text>
          </View>
        )}

        {/* WebView wrapped in ScrollView for pull-to-refresh */}
        <ScrollView
          contentContainerStyle={styles.scrollContent}
          refreshControl={
            <RefreshControl
              refreshing={isRefreshing}
              onRefresh={handleRefresh}
              tintColor="#4F46E5"
              colors={['#4F46E5']}
            />
          }
          scrollEnabled={false}
          style={styles.scrollView}
        >
          <WebView
            ref={webViewRef}
            source={{ uri: currentUrl }}
            style={styles.webView}
            // JavaScript injection
            injectedJavaScript={getInjectedJS()}
            injectedJavaScriptBeforeContentLoaded={`
              window.__DEXAI_NATIVE__ = true;
              window.__DEXAI_PLATFORM__ = '${Platform.OS}';
              true;
            `}
            // Message handling
            onMessage={handleMessage}
            // Navigation
            onNavigationStateChange={handleNavigationChange}
            onShouldStartLoadWithRequest={handleShouldStartLoad}
            // Loading states
            onLoadStart={handleLoadStart}
            onLoadEnd={handleLoadEnd}
            // Error handling
            onError={handleError}
            onHttpError={handleHttpError}
            // Settings
            javaScriptEnabled={true}
            domStorageEnabled={true}
            startInLoadingState={false}
            scalesPageToFit={true}
            allowsBackForwardNavigationGestures={true}
            allowsInlineMediaPlayback={true}
            mediaPlaybackRequiresUserAction={false}
            // Caching
            cacheEnabled={true}
            cacheMode="LOAD_DEFAULT"
            // Security
            originWhitelist={['https://*', 'http://localhost:*']}
            mixedContentMode="compatibility"
            // iOS specific
            allowsLinkPreview={false}
            automaticallyAdjustContentInsets={false}
            contentInsetAdjustmentBehavior="never"
            // Android specific
            overScrollMode="never"
            textZoom={100}
            setBuiltInZoomControls={false}
            setDisplayZoomControls={false}
            // Accessibility
            accessible={true}
            accessibilityLabel="DexAI Dashboard"
          />
        </ScrollView>
      </View>
    );
  }
);

WebViewContainer.displayName = 'WebViewContainer';

// =============================================================================
// Styles
// =============================================================================

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F9FAFB',
  },
  centerContent: {
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
  },
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    flex: 1,
  },
  webView: {
    flex: 1,
    backgroundColor: 'transparent',
  },
  loadingOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: '#F9FAFB',
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 10,
  },
  loadingText: {
    marginTop: 16,
    fontSize: 16,
    color: '#6B7280',
    fontWeight: '500',
  },
  errorTitle: {
    fontSize: 24,
    fontWeight: '700',
    color: '#111827',
    marginBottom: 12,
  },
  errorMessage: {
    fontSize: 16,
    color: '#6B7280',
    textAlign: 'center',
    marginBottom: 24,
    lineHeight: 24,
  },
  retryButton: {
    backgroundColor: '#4F46E5',
    paddingHorizontal: 32,
    paddingVertical: 14,
    borderRadius: 8,
  },
  retryButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
  },
});

// =============================================================================
// Exports
// =============================================================================

export default WebViewContainer;
