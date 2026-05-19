/**
 * SSE Chat hook for AI conversations.
 * 
 * Features:
 * - Server-Sent Events (SSE) streaming
 * - Parse token/citation/tool_call/done/denied events
 * - Accumulate streaming tokens into messages
 * - Handle errors and connection issues
 * 
 * Usage:
 * ```tsx
 * const { messages, send, isStreaming, error } = useChat(conversationId);
 * ```
 */

'use client';

import { useState, useCallback, useRef } from 'react';
import { useAuthStore } from '@/lib/store/auth';

// ============================================================================
// Types
// ============================================================================

interface Message {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant';
  content: string;
  citations: Citation[];
  tool_calls: ToolCall[];
  denied: boolean;
  denial_reason: string | null;
  created_at: string;
}

interface Citation {
  record_id: string;
  dataset: string;
  score: number;
}

interface ToolCall {
  name: string;
  args: Record<string, unknown>;
}

interface SSEEvent {
  event: string;
  data: Record<string, unknown>;
}

// ============================================================================
// Hook
// ============================================================================

export function useChat(conversationId: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const accessToken = useAuthStore((state) => state.accessToken);
  const abortControllerRef = useRef<AbortController | null>(null);

  const send = useCallback(async (text: string) => {
    if (!accessToken) {
      setError('未登录');
      return;
    }

    if (isStreaming) {
      console.warn('[useChat] Already streaming');
      return;
    }

    setIsStreaming(true);
    setError(null);

    // Add user message immediately
    const userMessage: Message = {
      id: `temp-user-${Date.now()}`,
      conversation_id: conversationId,
      role: 'user',
      content: text,
      citations: [],
      tool_calls: [],
      denied: false,
      denial_reason: null,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMessage]);

    // Prepare assistant message placeholder
    const assistantMessage: Message = {
      id: `temp-assistant-${Date.now()}`,
      conversation_id: conversationId,
      role: 'assistant',
      content: '',
      citations: [],
      tool_calls: [],
      denied: false,
      denial_reason: null,
      created_at: new Date().toISOString(),
    };

    try {
      // Create abort controller for cancellation
      abortControllerRef.current = new AbortController();

      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';
      const response = await fetch(`${apiUrl}/ai/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          conversation_id: conversationId,
          message: text,
        }),
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      if (!response.body) {
        throw new Error('Response body is null');
      }

      // Read SSE stream
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let currentMessage = { ...assistantMessage };

      // Add assistant message to state
      setMessages((prev) => [...prev, currentMessage]);

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.trim() || line.startsWith(':')) continue;

          try {
            const event = parseSSELine(line);
            if (!event) continue;

            // Handle different event types
            if (event.event === 'token') {
              // Append token to content
              const delta = event.data.delta as string;
              currentMessage = {
                ...currentMessage,
                content: currentMessage.content + delta,
              };
              setMessages((prev) => {
                const newMessages = [...prev];
                newMessages[newMessages.length - 1] = currentMessage;
                return newMessages;
              });
            } else if (event.event === 'citation') {
              // Add citation
              const citation: Citation = {
                record_id: event.data.record_id as string,
                dataset: event.data.dataset as string,
                score: event.data.score as number,
              };
              currentMessage = {
                ...currentMessage,
                citations: [...currentMessage.citations, citation],
              };
              setMessages((prev) => {
                const newMessages = [...prev];
                newMessages[newMessages.length - 1] = currentMessage;
                return newMessages;
              });
            } else if (event.event === 'tool_call') {
              // Add tool call
              const toolCall: ToolCall = {
                name: event.data.name as string,
                args: event.data.args as Record<string, unknown>,
              };
              currentMessage = {
                ...currentMessage,
                tool_calls: [...currentMessage.tool_calls, toolCall],
              };
              setMessages((prev) => {
                const newMessages = [...prev];
                newMessages[newMessages.length - 1] = currentMessage;
                return newMessages;
              });
            } else if (event.event === 'denied') {
              // Mark as denied
              currentMessage = {
                ...currentMessage,
                denied: true,
                denial_reason: event.data.detail as string || event.data.reason as string || null,
              };
              setMessages((prev) => {
                const newMessages = [...prev];
                newMessages[newMessages.length - 1] = currentMessage;
                return newMessages;
              });
            } else if (event.event === 'done') {
              // Finalize message with real ID
              const messageId = event.data.message_id as string;
              currentMessage = {
                ...currentMessage,
                id: messageId,
              };
              setMessages((prev) => {
                const newMessages = [...prev];
                newMessages[newMessages.length - 1] = currentMessage;
                return newMessages;
              });
            }
          } catch (err) {
            console.error('[useChat] Failed to parse SSE event:', err);
          }
        }
      }
    } catch (err) {
      if (err instanceof Error) {
        if (err.name === 'AbortError') {
          console.log('[useChat] Request aborted');
        } else {
          console.error('[useChat] Error:', err);
          setError(err.message);
        }
      } else {
        setError('发送消息失败');
      }
    } finally {
      setIsStreaming(false);
      abortControllerRef.current = null;
    }
  }, [conversationId, accessToken, isStreaming]);

  const cancel = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, []);

  return {
    messages,
    send,
    cancel,
    isStreaming,
    error,
  };
}

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Parse SSE line into event object
 */
function parseSSELine(line: string): SSEEvent | null {
  // SSE format: "event: <type>\ndata: <json>"
  // Or simplified: "data: <json>" (default event type is "message")
  
  if (line.startsWith('data: ')) {
    const dataStr = line.slice(6);
    try {
      const data = JSON.parse(dataStr);
      
      // Check if data has an "event" field (our custom format)
      if (typeof data === 'object' && data !== null && 'event' in data) {
        return {
          event: data.event as string,
          data: data.data as Record<string, unknown>,
        };
      }
      
      // Otherwise, treat entire data as the event
      return {
        event: 'message',
        data: data as Record<string, unknown>,
      };
    } catch (err) {
      console.error('[parseSSELine] Failed to parse JSON:', dataStr, err);
      return null;
    }
  }
  
  return null;
}

/**
 * Parse multiple SSE events from buffer
 */
export function parseSSE(text: string): SSEEvent[] {
  const events: SSEEvent[] = [];
  const lines = text.split('\n');
  
  for (const line of lines) {
    const event = parseSSELine(line);
    if (event) {
      events.push(event);
    }
  }
  
  return events;
}
