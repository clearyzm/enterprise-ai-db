/**
 * WebSocket client with automatic reconnection and exponential backoff.
 * 
 * Features:
 * - Auto-reconnect with exponential backoff (1s, 2s, 4s, 8s, max 30s)
 * - Token-based authentication via query parameter
 * - Event-based message handling
 * - Connection state management
 * - Graceful disconnect
 * 
 * Usage:
 * ```ts
 * const ws = new WSClient(token);
 * ws.on('message', (data) => console.log(data));
 * ws.connect();
 * // Later: ws.disconnect();
 * ```
 */

// ============================================================================
// Types
// ============================================================================

export type WSMessageType = 
  | 'subscribe'
  | 'unsubscribe'
  | 'record.upserted'
  | 'record.deleted'
  | 'approval.new'
  | 'approval.advanced'
  | 'approval.applied'
  | 'approval.rejected';

export interface WSMessage {
  type: WSMessageType;
  [key: string]: unknown;
}

export interface SubscribeMessage {
  type: 'subscribe';
  channels: string[];
}

export interface UnsubscribeMessage {
  type: 'unsubscribe';
  channels: string[];
}

type EventHandler = (data: WSMessage) => void;
type ConnectionStateHandler = (state: 'connecting' | 'connected' | 'disconnected' | 'error') => void;

// ============================================================================
// WebSocket Client
// ============================================================================

export class WSClient {
  private ws: WebSocket | null = null;
  private token: string;
  private url: string;
  private reconnectAttempts = 0;
  private maxReconnectDelay = 30000; // 30 seconds
  private reconnectTimer: NodeJS.Timeout | null = null;
  private intentionalDisconnect = false;
  private eventHandlers: Map<string, EventHandler[]> = new Map();
  private stateHandlers: ConnectionStateHandler[] = [];
  private subscribedChannels: Set<string> = new Set();

  constructor(token: string, url?: string) {
    this.token = token;
    this.url = url || process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws';
  }

  /**
   * Connect to WebSocket server
   */
  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      console.warn('[WSClient] Already connected');
      return;
    }

    this.intentionalDisconnect = false;
    this.notifyStateChange('connecting');

    try {
      // Append token as query parameter
      const wsUrl = `${this.url}?token=${encodeURIComponent(this.token)}`;
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = this.handleOpen.bind(this);
      this.ws.onmessage = this.handleMessage.bind(this);
      this.ws.onerror = this.handleError.bind(this);
      this.ws.onclose = this.handleClose.bind(this);
    } catch (error) {
      console.error('[WSClient] Connection error:', error);
      this.notifyStateChange('error');
      this.scheduleReconnect();
    }
  }

  /**
   * Disconnect from WebSocket server
   */
  disconnect(): void {
    this.intentionalDisconnect = true;
    this.clearReconnectTimer();
    
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    this.notifyStateChange('disconnected');
  }

  /**
   * Subscribe to channels
   */
  subscribe(channels: string[]): void {
    channels.forEach(ch => this.subscribedChannels.add(ch));

    if (this.ws?.readyState === WebSocket.OPEN) {
      const message: SubscribeMessage = {
        type: 'subscribe',
        channels,
      };
      this.send(message);
    }
  }

  /**
   * Unsubscribe from channels
   */
  unsubscribe(channels: string[]): void {
    channels.forEach(ch => this.subscribedChannels.delete(ch));

    if (this.ws?.readyState === WebSocket.OPEN) {
      const message: UnsubscribeMessage = {
        type: 'unsubscribe',
        channels,
      };
      this.send(message);
    }
  }

  /**
   * Register event handler
   */
  on(event: string, handler: EventHandler): void {
    if (!this.eventHandlers.has(event)) {
      this.eventHandlers.set(event, []);
    }
    this.eventHandlers.get(event)!.push(handler);
  }

  /**
   * Unregister event handler
   */
  off(event: string, handler: EventHandler): void {
    const handlers = this.eventHandlers.get(event);
    if (handlers) {
      const index = handlers.indexOf(handler);
      if (index !== -1) {
        handlers.splice(index, 1);
      }
    }
  }

  /**
   * Register connection state handler
   */
  onStateChange(handler: ConnectionStateHandler): void {
    this.stateHandlers.push(handler);
  }

  /**
   * Send message to server
   */
  private send(message: WSMessage | SubscribeMessage | UnsubscribeMessage): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    } else {
      console.warn('[WSClient] Cannot send message: not connected');
    }
  }

  /**
   * Handle WebSocket open event
   */
  private handleOpen(): void {
    console.log('[WSClient] Connected');
    this.reconnectAttempts = 0;
    this.notifyStateChange('connected');

    // Re-subscribe to channels after reconnect
    if (this.subscribedChannels.size > 0) {
      this.subscribe(Array.from(this.subscribedChannels));
    }
  }

  /**
   * Handle WebSocket message event
   */
  private handleMessage(event: MessageEvent): void {
    try {
      const data = JSON.parse(event.data) as WSMessage;
      
      // Emit to specific event handlers
      const handlers = this.eventHandlers.get(data.type);
      if (handlers) {
        handlers.forEach(handler => handler(data));
      }

      // Emit to wildcard handlers
      const wildcardHandlers = this.eventHandlers.get('*');
      if (wildcardHandlers) {
        wildcardHandlers.forEach(handler => handler(data));
      }
    } catch (error) {
      console.error('[WSClient] Failed to parse message:', error);
    }
  }

  /**
   * Handle WebSocket error event
   */
  private handleError(event: Event): void {
    console.error('[WSClient] Error:', event);
    this.notifyStateChange('error');
  }

  /**
   * Handle WebSocket close event
   */
  private handleClose(event: CloseEvent): void {
    console.log('[WSClient] Disconnected:', event.code, event.reason);
    this.ws = null;
    this.notifyStateChange('disconnected');

    // Reconnect if not intentional disconnect
    if (!this.intentionalDisconnect) {
      this.scheduleReconnect();
    }
  }

  /**
   * Schedule reconnection with exponential backoff
   */
  private scheduleReconnect(): void {
    this.clearReconnectTimer();

    // Calculate delay: 1s, 2s, 4s, 8s, 16s, 30s (max)
    const delay = Math.min(
      1000 * Math.pow(2, this.reconnectAttempts),
      this.maxReconnectDelay
    );

    console.log(`[WSClient] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts + 1})`);

    this.reconnectTimer = setTimeout(() => {
      this.reconnectAttempts++;
      this.connect();
    }, delay);
  }

  /**
   * Clear reconnect timer
   */
  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  /**
   * Notify state change handlers
   */
  private notifyStateChange(state: 'connecting' | 'connected' | 'disconnected' | 'error'): void {
    this.stateHandlers.forEach(handler => handler(state));
  }

  /**
   * Get current connection state
   */
  get state(): 'connecting' | 'connected' | 'disconnected' | 'error' {
    if (!this.ws) return 'disconnected';
    
    switch (this.ws.readyState) {
      case WebSocket.CONNECTING:
        return 'connecting';
      case WebSocket.OPEN:
        return 'connected';
      case WebSocket.CLOSING:
      case WebSocket.CLOSED:
        return 'disconnected';
      default:
        return 'disconnected';
    }
  }
}

// ============================================================================
// Singleton Instance (optional)
// ============================================================================

let wsClientInstance: WSClient | null = null;

/**
 * Get or create singleton WebSocket client instance
 */
export function getWSClient(token: string): WSClient {
  if (!wsClientInstance) {
    wsClientInstance = new WSClient(token);
  }
  return wsClientInstance;
}

/**
 * Destroy singleton instance
 */
export function destroyWSClient(): void {
  if (wsClientInstance) {
    wsClientInstance.disconnect();
    wsClientInstance = null;
  }
}
