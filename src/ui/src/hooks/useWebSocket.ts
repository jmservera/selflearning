import { useState, useEffect, useRef, useCallback } from 'react';
import type { WSMessage } from '@/lib/types';
import { getWebSocketUrl } from '@/lib/api';

interface UseWebSocketOptions {
  path: string;
  onMessage?: (message: WSMessage) => void;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  heartbeatInterval?: number;
}

interface UseWebSocketReturn {
  messages: WSMessage[];
  isConnected: boolean;
  lastMessage: WSMessage | null;
  send: (data: unknown) => void;
}

export function useWebSocket({
  path,
  onMessage,
  reconnectInterval = 3000,
  maxReconnectAttempts = 10,
  heartbeatInterval = 25000,
}: UseWebSocketOptions): UseWebSocketReturn {
  const [messages, setMessages] = useState<WSMessage[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);
  
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>();
  const heartbeatIntervalRef = useRef<NodeJS.Timeout>();

  const send = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  const startHeartbeat = useCallback(() => {
    if (heartbeatIntervalRef.current) {
      clearInterval(heartbeatIntervalRef.current);
    }
    
    heartbeatIntervalRef.current = setInterval(() => {
      send({ type: 'ping' });
    }, heartbeatInterval);
  }, [send, heartbeatInterval]);

  const stopHeartbeat = useCallback(() => {
    if (heartbeatIntervalRef.current) {
      clearInterval(heartbeatIntervalRef.current);
      heartbeatIntervalRef.current = undefined;
    }
  }, []);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    try {
      const ws = new WebSocket(getWebSocketUrl(path));

      ws.onopen = () => {
        console.log(`WebSocket connected: ${path}`);
        setIsConnected(true);
        reconnectAttemptsRef.current = 0;
        startHeartbeat();
      };

      ws.onmessage = (event) => {
        try {
          const message: WSMessage = JSON.parse(event.data);
          setLastMessage(message);
          setMessages((prev) => [...prev, message]);
          onMessage?.(message);
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };

      ws.onerror = (error) => {
        console.error(`WebSocket error on ${path}:`, error);
      };

      ws.onclose = () => {
        console.log(`WebSocket closed: ${path}`);
        setIsConnected(false);
        stopHeartbeat();
        wsRef.current = null;

        if (reconnectAttemptsRef.current < maxReconnectAttempts) {
          const delay = Math.min(
            reconnectInterval * Math.pow(2, reconnectAttemptsRef.current),
            30000
          );
          
          reconnectAttemptsRef.current += 1;
          console.log(
            `Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current}/${maxReconnectAttempts})`
          );
          
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, delay);
        }
      };

      wsRef.current = ws;
    } catch (error) {
      console.error('Failed to create WebSocket:', error);
    }
  }, [path, reconnectInterval, maxReconnectAttempts, onMessage, startHeartbeat, stopHeartbeat]);

  useEffect(() => {
    connect();

    return () => {
      stopHeartbeat();
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect, stopHeartbeat]);

  return {
    messages,
    isConnected,
    lastMessage,
    send,
  };
}
