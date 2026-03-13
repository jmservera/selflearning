import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useWebSocket } from '../useWebSocket';
import type { WSMessage } from '@/lib/types';

// --- Mock WebSocket Implementation ---

class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  url: string;
  readyState: number = MockWebSocket.CONNECTING;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send = vi.fn();

  close() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ code: 1000, reason: 'Normal closure' } as CloseEvent);
  }

  // Helpers to simulate server-side events in tests
  simulateOpen() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.(new Event('open'));
  }

  simulateMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent);
  }

  simulateError() {
    this.onerror?.(new Event('error'));
  }

  simulateClose(code = 1000) {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ code } as CloseEvent);
  }

  static instances: MockWebSocket[] = [];

  static reset() {
    MockWebSocket.instances = [];
  }

  static latest(): MockWebSocket {
    return MockWebSocket.instances[MockWebSocket.instances.length - 1];
  }
}

describe('useWebSocket', () => {
  beforeEach(() => {
    MockWebSocket.reset();
    vi.useFakeTimers();
    vi.stubGlobal('WebSocket', MockWebSocket);
  });

  afterEach(() => {
    // Clean up any pending timers before restoring real timers
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it('starts disconnected before the socket opens', () => {
    const { result } = renderHook(() =>
      useWebSocket({ path: '/ws/test', maxReconnectAttempts: 0 })
    );
    expect(result.current.isConnected).toBe(false);
    expect(result.current.messages).toEqual([]);
    expect(result.current.lastMessage).toBeNull();
  });

  it('creates a WebSocket connection on mount', () => {
    renderHook(() => useWebSocket({ path: '/ws/test', maxReconnectAttempts: 0 }));
    expect(MockWebSocket.instances).toHaveLength(1);
    expect(MockWebSocket.instances[0].url).toContain('/ws/test');
  });

  it('sets isConnected to true when the socket opens', () => {
    const { result } = renderHook(() =>
      useWebSocket({ path: '/ws/status', maxReconnectAttempts: 0 })
    );
    // act() flushes all synchronous React state updates triggered inside it
    act(() => { MockWebSocket.latest().simulateOpen(); });
    expect(result.current.isConnected).toBe(true);
  });

  it('sets isConnected to false when the socket closes', () => {
    const { result } = renderHook(() =>
      useWebSocket({ path: '/ws/status', maxReconnectAttempts: 0 })
    );
    act(() => { MockWebSocket.latest().simulateOpen(); });
    expect(result.current.isConnected).toBe(true);

    act(() => { MockWebSocket.latest().simulateClose(); });
    expect(result.current.isConnected).toBe(false);
  });

  it('appends received messages to the messages array', () => {
    const message: WSMessage = {
      type: 'status_update',
      data: { active_topics: 3 },
      timestamp: '2024-01-01T00:00:00Z',
    };

    const { result } = renderHook(() =>
      useWebSocket({ path: '/ws/status', maxReconnectAttempts: 0 })
    );
    act(() => {
      MockWebSocket.latest().simulateOpen();
      MockWebSocket.latest().simulateMessage(message);
    });

    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0]).toEqual(message);
    expect(result.current.lastMessage).toEqual(message);
  });

  it('calls the onMessage callback when a message is received', () => {
    const onMessage = vi.fn();
    const message: WSMessage = {
      type: 'log_entry',
      data: {},
      timestamp: '2024-01-01T00:00:00Z',
    };

    renderHook(() =>
      useWebSocket({ path: '/ws/logs', onMessage, maxReconnectAttempts: 0 })
    );
    act(() => {
      MockWebSocket.latest().simulateOpen();
      MockWebSocket.latest().simulateMessage(message);
    });

    expect(onMessage).toHaveBeenCalledWith(message);
  });

  it('ignores malformed JSON messages without crashing', () => {
    const { result } = renderHook(() =>
      useWebSocket({ path: '/ws/test', maxReconnectAttempts: 0 })
    );
    act(() => {
      MockWebSocket.latest().simulateOpen();
      // Simulate malformed JSON
      MockWebSocket.latest().onmessage?.({ data: 'not-valid-json' } as MessageEvent);
    });
    // Should not crash and messages should remain empty
    expect(result.current.messages).toHaveLength(0);
  });

  it('does not send when socket is not open', () => {
    const { result } = renderHook(() =>
      useWebSocket({ path: '/ws/test', maxReconnectAttempts: 0 })
    );
    act(() => { result.current.send({ type: 'ping' }); });
    expect(MockWebSocket.latest().send).not.toHaveBeenCalled();
  });

  it('sends data when socket is open', () => {
    const { result } = renderHook(() =>
      useWebSocket({ path: '/ws/test', maxReconnectAttempts: 0 })
    );
    act(() => { MockWebSocket.latest().simulateOpen(); });
    expect(result.current.isConnected).toBe(true);

    act(() => { result.current.send({ type: 'ping' }); });
    expect(MockWebSocket.latest().send).toHaveBeenCalledWith(JSON.stringify({ type: 'ping' }));
  });

  it('starts a heartbeat after connection opens', () => {
    renderHook(() =>
      useWebSocket({ path: '/ws/test', heartbeatInterval: 1000, maxReconnectAttempts: 0 })
    );
    act(() => { MockWebSocket.latest().simulateOpen(); });
    // Advance past one heartbeat interval
    act(() => { vi.advanceTimersByTime(1000); });
    expect(MockWebSocket.latest().send).toHaveBeenCalledWith(JSON.stringify({ type: 'ping' }));
  });

  it('schedules reconnect after socket closes (when attempts remain)', () => {
    renderHook(() =>
      useWebSocket({ path: '/ws/test', reconnectInterval: 500, maxReconnectAttempts: 3 })
    );
    act(() => { MockWebSocket.latest().simulateOpen(); });

    act(() => { MockWebSocket.latest().simulateClose(1006); });
    // Before the timer fires, still only one socket
    expect(MockWebSocket.instances).toHaveLength(1);

    // Advance past the first reconnect interval
    act(() => { vi.advanceTimersByTime(600); });
    expect(MockWebSocket.instances).toHaveLength(2);
  });

  it('stops reconnecting after maxReconnectAttempts', () => {
    renderHook(() =>
      useWebSocket({ path: '/ws/test', reconnectInterval: 100, maxReconnectAttempts: 1 })
    );
    act(() => { MockWebSocket.latest().simulateOpen(); });

    // First disconnect → schedules reconnect
    act(() => { MockWebSocket.latest().simulateClose(1006); });
    act(() => { vi.advanceTimersByTime(200); });
    expect(MockWebSocket.instances).toHaveLength(2);

    // Second disconnect → no more reconnects (max 1 attempt used)
    act(() => { MockWebSocket.latest().simulateClose(1006); });
    act(() => { vi.advanceTimersByTime(10000); });
    // Still only 2 sockets
    expect(MockWebSocket.instances).toHaveLength(2);
  });

  it('cleans up socket and timers on unmount', () => {
    const { unmount } = renderHook(() =>
      useWebSocket({ path: '/ws/test', maxReconnectAttempts: 0 })
    );
    act(() => { MockWebSocket.latest().simulateOpen(); });
    const ws = MockWebSocket.latest();
    const closeSpy = vi.spyOn(ws, 'close');
    unmount();
    expect(closeSpy).toHaveBeenCalled();
  });

  it('handles onerror event without crashing', () => {
    const { result } = renderHook(() =>
      useWebSocket({ path: '/ws/test', maxReconnectAttempts: 0 })
    );
    act(() => {
      MockWebSocket.latest().simulateOpen();
      MockWebSocket.latest().simulateError();
    });
    // Connection status should not change on error alone (only onclose changes it)
    expect(result.current.isConnected).toBe(true);
  });

  it('accumulates multiple messages', () => {
    const msg1: WSMessage = { type: 'status_update', data: {}, timestamp: '2024-01-01T00:00:00Z' };
    const msg2: WSMessage = { type: 'log_entry', data: {}, timestamp: '2024-01-01T00:00:01Z' };

    const { result } = renderHook(() =>
      useWebSocket({ path: '/ws/test', maxReconnectAttempts: 0 })
    );
    act(() => {
      MockWebSocket.latest().simulateOpen();
      MockWebSocket.latest().simulateMessage(msg1);
      MockWebSocket.latest().simulateMessage(msg2);
    });

    expect(result.current.messages).toHaveLength(2);
    expect(result.current.lastMessage).toEqual(msg2);
  });
});

