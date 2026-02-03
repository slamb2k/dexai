/**
 * DexAI Mobile - WebView Bridge
 *
 * Handles bidirectional communication between the native Expo app
 * and the PWA dashboard running in the WebView.
 *
 * Communication Protocol:
 * - Native -> WebView: window.postMessage() via injectedJavaScript
 * - WebView -> Native: window.ReactNativeWebView.postMessage()
 */

import { WebView } from 'react-native-webview';
import {
  BridgeMessage,
  BridgeCommandToWeb,
  BridgeCommandFromWeb,
  AuthTokenPayload,
  NavigationPayload,
  DeviceInfoPayload,
  NotificationData,
} from '../types';
import { debugLog, debugError } from './config';

// =============================================================================
// Types
// =============================================================================

type MessageHandler = (message: BridgeMessage) => void;
type WebViewRef = React.RefObject<WebView>;

// =============================================================================
// Bridge Class
// =============================================================================

/**
 * WebView Bridge for native-to-web communication
 */
class WebViewBridge {
  private webViewRef: WebViewRef | null = null;
  private handlers: Map<BridgeCommandFromWeb, MessageHandler[]> = new Map();
  private pendingMessages: BridgeMessage[] = [];
  private isWebViewReady = false;
  private messageIdCounter = 0;

  /**
   * Set the WebView ref for communication
   */
  setWebViewRef(ref: WebViewRef): void {
    this.webViewRef = ref;
    debugLog('Bridge: WebView ref set');
  }

  /**
   * Mark WebView as ready to receive messages
   */
  setReady(ready: boolean): void {
    this.isWebViewReady = ready;
    debugLog('Bridge: WebView ready =', ready);

    if (ready) {
      this.flushPendingMessages();
    }
  }

  /**
   * Generate unique message ID
   */
  private generateMessageId(): string {
    return `msg_${Date.now()}_${++this.messageIdCounter}`;
  }

  /**
   * Flush pending messages after WebView becomes ready
   */
  private flushPendingMessages(): void {
    if (!this.isWebViewReady || this.pendingMessages.length === 0) {
      return;
    }

    debugLog(`Bridge: Flushing ${this.pendingMessages.length} pending messages`);

    while (this.pendingMessages.length > 0) {
      const message = this.pendingMessages.shift();
      if (message) {
        this.postToWebView(message);
      }
    }
  }

  /**
   * Post message to WebView
   */
  private postToWebView(message: BridgeMessage): boolean {
    if (!this.webViewRef?.current) {
      debugError('Bridge: No WebView ref available');
      return false;
    }

    const script = `
      (function() {
        if (window.onDexAIMessage) {
          window.onDexAIMessage(${JSON.stringify(message)});
        } else {
          window.postMessage(${JSON.stringify(message)}, '*');
        }
      })();
      true;
    `;

    this.webViewRef.current.injectJavaScript(script);
    debugLog('Bridge: Posted message to WebView', message.command);
    return true;
  }

  /**
   * Send message to WebView (queues if not ready)
   */
  send<T>(command: BridgeCommandToWeb, payload: T): string {
    const message: BridgeMessage<T> = {
      command,
      payload,
      messageId: this.generateMessageId(),
      timestamp: Date.now(),
    };

    if (!this.isWebViewReady) {
      debugLog('Bridge: Queueing message (WebView not ready)', command);
      this.pendingMessages.push(message);
      return message.messageId!;
    }

    this.postToWebView(message);
    return message.messageId!;
  }

  /**
   * Register handler for messages from WebView
   */
  on(command: BridgeCommandFromWeb, handler: MessageHandler): () => void {
    const handlers = this.handlers.get(command) || [];
    handlers.push(handler);
    this.handlers.set(command, handlers);

    // Return unsubscribe function
    return () => {
      const currentHandlers = this.handlers.get(command) || [];
      const index = currentHandlers.indexOf(handler);
      if (index > -1) {
        currentHandlers.splice(index, 1);
      }
    };
  }

  /**
   * Handle message received from WebView
   */
  handleMessage(data: string): void {
    try {
      const message = JSON.parse(data) as BridgeMessage;
      debugLog('Bridge: Received message', message.command);

      const handlers = this.handlers.get(message.command as BridgeCommandFromWeb) || [];
      handlers.forEach((handler) => handler(message));
    } catch (error) {
      debugError('Bridge: Failed to parse message', error);
    }
  }

  /**
   * Clear all handlers and pending messages
   */
  reset(): void {
    this.handlers.clear();
    this.pendingMessages = [];
    this.isWebViewReady = false;
    debugLog('Bridge: Reset');
  }
}

// =============================================================================
// Singleton Instance
// =============================================================================

export const bridge = new WebViewBridge();

// =============================================================================
// Convenience Functions
// =============================================================================

/**
 * Send auth token to WebView
 */
export const sendAuthToken = (payload: AuthTokenPayload): string => {
  return bridge.send('AUTH_TOKEN', payload);
};

/**
 * Navigate WebView to a path
 */
export const navigateWebView = (payload: NavigationPayload): string => {
  return bridge.send('NAVIGATE', payload);
};

/**
 * Notify WebView of received notification
 */
export const notifyNotificationReceived = (notification: NotificationData): string => {
  return bridge.send('NOTIFICATION_RECEIVED', notification);
};

/**
 * Update badge count in WebView
 */
export const updateBadge = (count: number): string => {
  return bridge.send('BADGE_UPDATE', { count });
};

/**
 * Send device info to WebView
 */
export const sendDeviceInfo = (info: DeviceInfoPayload): string => {
  return bridge.send('DEVICE_INFO', info);
};

/**
 * Notify WebView of theme change
 */
export const notifyThemeChange = (theme: 'light' | 'dark' | 'system'): string => {
  return bridge.send('THEME_CHANGE', { theme });
};

// =============================================================================
// Injected JavaScript
// =============================================================================

/**
 * JavaScript to inject into WebView on load
 * Sets up the bridge receiver on the web side
 */
export const getInjectedJavaScript = (): string => `
  (function() {
    // Prevent duplicate initialization
    if (window.__DEXAI_BRIDGE_INITIALIZED__) {
      return;
    }
    window.__DEXAI_BRIDGE_INITIALIZED__ = true;

    // Message queue for before handlers are ready
    window.__DEXAI_MESSAGE_QUEUE__ = [];

    // Handler registration
    window.onDexAIMessage = function(message) {
      console.log('[DexAI Bridge] Received:', message.command);

      // Dispatch to registered handlers
      if (window.__DEXAI_HANDLERS__ && window.__DEXAI_HANDLERS__[message.command]) {
        window.__DEXAI_HANDLERS__[message.command].forEach(function(handler) {
          try {
            handler(message.payload, message);
          } catch (e) {
            console.error('[DexAI Bridge] Handler error:', e);
          }
        });
      } else {
        // Queue message if no handlers yet
        window.__DEXAI_MESSAGE_QUEUE__.push(message);
      }
    };

    // Register handler for a command
    window.registerDexAIHandler = function(command, handler) {
      window.__DEXAI_HANDLERS__ = window.__DEXAI_HANDLERS__ || {};
      window.__DEXAI_HANDLERS__[command] = window.__DEXAI_HANDLERS__[command] || [];
      window.__DEXAI_HANDLERS__[command].push(handler);

      // Process any queued messages for this command
      window.__DEXAI_MESSAGE_QUEUE__ = window.__DEXAI_MESSAGE_QUEUE__.filter(function(msg) {
        if (msg.command === command) {
          handler(msg.payload, msg);
          return false;
        }
        return true;
      });
    };

    // Send message to native app
    window.sendToNative = function(command, payload) {
      if (window.ReactNativeWebView) {
        window.ReactNativeWebView.postMessage(JSON.stringify({
          command: command,
          payload: payload,
          timestamp: Date.now()
        }));
      } else {
        console.warn('[DexAI Bridge] ReactNativeWebView not available');
      }
    };

    // Notify native that bridge is ready
    window.sendToNative('READY', { timestamp: Date.now() });

    // Intercept console for native logging
    var originalConsole = {
      log: console.log,
      warn: console.warn,
      error: console.error
    };

    console.log = function() {
      originalConsole.log.apply(console, arguments);
      window.sendToNative('LOG', { level: 'log', args: Array.from(arguments) });
    };

    console.warn = function() {
      originalConsole.warn.apply(console, arguments);
      window.sendToNative('LOG', { level: 'warn', args: Array.from(arguments) });
    };

    console.error = function() {
      originalConsole.error.apply(console, arguments);
      window.sendToNative('LOG', { level: 'error', args: Array.from(arguments) });
    };

    console.log('[DexAI Bridge] Initialized');
  })();
  true;
`;

// =============================================================================
// Exports
// =============================================================================

export default bridge;
