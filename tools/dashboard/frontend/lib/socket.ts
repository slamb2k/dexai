/**
 * WebSocket Client for DexAI Dashboard
 *
 * Handles real-time updates for avatar state, activity, and metrics.
 */

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8080/ws';

type EventCallback<T = unknown> = (data: T) => void;

export interface DexStateEvent {
  state: string;
  task?: string;
}

export interface ActivityNewEvent {
  id: string;
  type: 'message' | 'task' | 'system' | 'error' | 'llm' | 'security';
  timestamp: string;
  summary: string;
  channel?: string;
  details?: string;
  severity?: 'info' | 'warning' | 'error';
}

export interface MetricsUpdateEvent {
  tasksToday: number;
  messagesToday: number;
  costToday: number;
}

class SocketClient {
  private ws: WebSocket | null = null;
  private reconnectTimeout: NodeJS.Timeout | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 2000;
  private listeners: Map<string, Set<EventCallback>> = new Map();

  /**
   * Connect to WebSocket server
   */
  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return; // Already connected
    }

    try {
      this.ws = new WebSocket(WS_URL);

      this.ws.onopen = () => {
        console.log('[Socket] Connected to WebSocket server');
        this.reconnectAttempts = 0;
        this.emit('connect', null);
      };

      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          const { type, data } = message;

          // Emit event to all registered listeners
          this.emit(type, data);
        } catch (error) {
          console.error('[Socket] Error parsing message:', error);
        }
      };

      this.ws.onerror = (error) => {
        console.error('[Socket] WebSocket error:', error);
      };

      this.ws.onclose = () => {
        console.log('[Socket] Disconnected from WebSocket server');
        this.emit('disconnect', null);
        this.scheduleReconnect();
      };
    } catch (error) {
      console.error('[Socket] Error connecting to WebSocket:', error);
      this.scheduleReconnect();
    }
  }

  /**
   * Disconnect from WebSocket server
   */
  disconnect(): void {
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    this.reconnectAttempts = 0;
  }

  /**
   * Schedule reconnection attempt
   */
  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.warn('[Socket] Max reconnect attempts reached');
      return;
    }

    this.reconnectAttempts++;
    const delay = this.reconnectDelay * this.reconnectAttempts;

    console.log(`[Socket] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

    this.reconnectTimeout = setTimeout(() => {
      this.connect();
    }, delay);
  }

  /**
   * Register event listener
   */
  private on<T>(event: string, callback: EventCallback<T>): () => void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }

    this.listeners.get(event)!.add(callback as EventCallback);

    // Return unsubscribe function
    return () => {
      const listeners = this.listeners.get(event);
      if (listeners) {
        listeners.delete(callback as EventCallback);
        if (listeners.size === 0) {
          this.listeners.delete(event);
        }
      }
    };
  }

  /**
   * Emit event to all listeners
   */
  private emit<T>(event: string, data: T): void {
    const listeners = this.listeners.get(event);
    if (listeners) {
      listeners.forEach((callback) => {
        try {
          callback(data);
        } catch (error) {
          console.error(`[Socket] Error in ${event} listener:`, error);
        }
      });
    }
  }

  // Public event subscription methods
  onConnect(callback: EventCallback<null>): () => void {
    return this.on('connect', callback);
  }

  onDisconnect(callback: EventCallback<null>): () => void {
    return this.on('disconnect', callback);
  }

  onDexState(callback: EventCallback<DexStateEvent>): () => void {
    return this.on('dex:state', callback);
  }

  onActivityNew(callback: EventCallback<ActivityNewEvent>): () => void {
    return this.on('activity:new', callback);
  }

  onMetricsUpdate(callback: EventCallback<MetricsUpdateEvent>): () => void {
    return this.on('metrics:update', callback);
  }

  /**
   * Send message to server
   */
  send(type: string, data: unknown): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type, data }));
    } else {
      console.warn('[Socket] Cannot send message: WebSocket not connected');
    }
  }

  /**
   * Get connection status
   */
  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

// Export singleton instance
export const socketClient = new SocketClient();

// Export class for custom instances
export { SocketClient };
