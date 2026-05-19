/**
 * WebSocket React hook for real-time updates.
 * 
 * Features:
 * - Automatic connection management
 * - Subscribe to channels
 * - Invalidate React Query cache on events
 * - Connection state tracking
 * 
 * Usage:
 * ```tsx
 * function MyComponent() {
 *   const { isConnected } = useWS(['dataset:abc123', 'approvals']);
 *   return <div>Status: {isConnected ? 'Connected' : 'Disconnected'}</div>;
 * }
 * ```
 */

'use client';

import { useEffect, useState, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '@/lib/store/auth';
import { WSClient, WSMessage } from '@/lib/ws';

// ============================================================================
// Types
// ============================================================================

interface UseWSOptions {
  enabled?: boolean;
  onMessage?: (message: WSMessage) => void;
}

interface UseWSReturn {
  isConnected: boolean;
  isConnecting: boolean;
  error: boolean;
}

// ============================================================================
// Hook
// ============================================================================

export function useWS(channels: string[] = [], options: UseWSOptions = {}): UseWSReturn {
  const { enabled = true, onMessage } = options;
  const queryClient = useQueryClient();
  const accessToken = useAuthStore((state) => state.accessToken);
  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [error, setError] = useState(false);
  const wsRef = useRef<WSClient | null>(null);

  useEffect(() => {
    // Don't connect if disabled or no token
    if (!enabled || !accessToken) {
      return;
    }

    // Create WebSocket client
    const ws = new WSClient(accessToken);
    wsRef.current = ws;

    // Handle connection state changes
    ws.onStateChange((state) => {
      setIsConnecting(state === 'connecting');
      setIsConnected(state === 'connected');
      setError(state === 'error');
    });

    // Handle record.upserted event
    ws.on('record.upserted', (data) => {
      console.log('[useWS] record.upserted:', data);
      
      // Invalidate records query for the dataset
      if ('dataset_id' in data && typeof data.dataset_id === 'string') {
        queryClient.invalidateQueries({ queryKey: ['records', data.dataset_id] });
      }
      
      // Call custom handler
      if (onMessage) {
        onMessage(data);
      }
    });

    // Handle record.deleted event
    ws.on('record.deleted', (data) => {
      console.log('[useWS] record.deleted:', data);
      
      // Invalidate records query for the dataset
      if ('dataset_id' in data && typeof data.dataset_id === 'string') {
        queryClient.invalidateQueries({ queryKey: ['records', data.dataset_id] });
      }
      
      // Call custom handler
      if (onMessage) {
        onMessage(data);
      }
    });

    // Handle approval.new event
    ws.on('approval.new', (data) => {
      console.log('[useWS] approval.new:', data);
      
      // Invalidate approvals queries
      queryClient.invalidateQueries({ queryKey: ['approvals'] });
      
      // Call custom handler
      if (onMessage) {
        onMessage(data);
      }
    });

    // Handle approval.advanced event
    ws.on('approval.advanced', (data) => {
      console.log('[useWS] approval.advanced:', data);
      
      // Invalidate approvals queries
      queryClient.invalidateQueries({ queryKey: ['approvals'] });
      
      // Invalidate specific approval detail
      if ('version_id' in data && typeof data.version_id === 'string') {
        queryClient.invalidateQueries({ queryKey: ['approval', data.version_id] });
      }
      
      // Call custom handler
      if (onMessage) {
        onMessage(data);
      }
    });

    // Handle approval.applied event
    ws.on('approval.applied', (data) => {
      console.log('[useWS] approval.applied:', data);
      
      // Invalidate approvals queries
      queryClient.invalidateQueries({ queryKey: ['approvals'] });
      
      // Invalidate specific approval detail
      if ('version_id' in data && typeof data.version_id === 'string') {
        queryClient.invalidateQueries({ queryKey: ['approval', data.version_id] });
      }
      
      // Invalidate records query if record_id is present
      if ('record_id' in data && typeof data.record_id === 'string' && 'dataset_id' in data && typeof data.dataset_id === 'string') {
        queryClient.invalidateQueries({ queryKey: ['records', data.dataset_id] });
      }
      
      // Call custom handler
      if (onMessage) {
        onMessage(data);
      }
    });

    // Handle approval.rejected event
    ws.on('approval.rejected', (data) => {
      console.log('[useWS] approval.rejected:', data);
      
      // Invalidate approvals queries
      queryClient.invalidateQueries({ queryKey: ['approvals'] });
      
      // Invalidate specific approval detail
      if ('version_id' in data && typeof data.version_id === 'string') {
        queryClient.invalidateQueries({ queryKey: ['approval', data.version_id] });
      }
      
      // Call custom handler
      if (onMessage) {
        onMessage(data);
      }
    });

    // Connect
    ws.connect();

    // Subscribe to channels
    if (channels.length > 0) {
      ws.subscribe(channels);
    }

    // Cleanup on unmount
    return () => {
      ws.disconnect();
      wsRef.current = null;
    };
  }, [enabled, accessToken, queryClient, onMessage, channels.join(',')]);

  return {
    isConnected,
    isConnecting,
    error,
  };
}

// ============================================================================
// Specialized Hooks
// ============================================================================

/**
 * Subscribe to dataset updates
 */
export function useDatasetWS(datasetId: string, enabled = true): UseWSReturn {
  return useWS([`dataset:${datasetId}`], { enabled });
}

/**
 * Subscribe to approval updates
 */
export function useApprovalsWS(enabled = true): UseWSReturn {
  return useWS(['approvals'], { enabled });
}

/**
 * Subscribe to AI conversation updates
 */
export function useAIConversationWS(conversationId: string, enabled = true): UseWSReturn {
  return useWS([`ai:${conversationId}`], { enabled });
}
