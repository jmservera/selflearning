import { render, screen, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ActivityLog } from '../ActivityLog';
import type { ActivityLog as ActivityLogType, WSMessage } from '@/lib/types';

type OnMessageFn = (message: WSMessage) => void;
type UseWebSocketOptions = { path: string; onMessage?: OnMessageFn };
type UseWebSocketReturn = { messages: WSMessage[]; isConnected: boolean; lastMessage: WSMessage | null; send: (data: unknown) => void };

const { useWebSocket } = vi.hoisted(() => ({
  useWebSocket: vi.fn((_opts: UseWebSocketOptions): UseWebSocketReturn => ({
    messages: [],
    isConnected: false,
    lastMessage: null,
    send: vi.fn(),
  })),
}));

vi.mock('@/hooks/useWebSocket', () => ({ useWebSocket }));

const sampleLogs: ActivityLogType[] = [
  {
    id: 'log-1',
    timestamp: '2024-01-01T10:00:00Z',
    service: 'scraper',
    action: 'scrape_complete',
    details: 'Scraped 10 pages from example.com',
    topic: 'machine-learning',
    success: true,
  },
  {
    id: 'log-2',
    timestamp: '2024-01-01T10:01:00Z',
    service: 'extractor',
    action: 'extraction_failed',
    details: 'Failed to parse PDF document',
    topic: null,
    success: false,
  },
  {
    id: 'log-3',
    timestamp: '2024-01-01T10:02:00Z',
    service: 'knowledge',
    action: 'entity_created',
    details: 'Created entity: Neural Network',
    topic: 'ai',
    success: true,
  },
];

describe('ActivityLog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the Activity Log heading', () => {
    render(<ActivityLog initialLogs={sampleLogs} />);
    expect(screen.getByText('Activity Log')).toBeInTheDocument();
  });

  it('shows "No activity yet" when logs are empty', () => {
    render(<ActivityLog initialLogs={[]} />);
    expect(screen.getByText('No activity yet')).toBeInTheDocument();
  });

  it('renders all log entries', () => {
    render(<ActivityLog initialLogs={sampleLogs} />);
    expect(screen.getByText('scraper')).toBeInTheDocument();
    expect(screen.getByText('extractor')).toBeInTheDocument();
    expect(screen.getByText('knowledge')).toBeInTheDocument();
  });

  it('renders action labels', () => {
    render(<ActivityLog initialLogs={sampleLogs} />);
    expect(screen.getByText('scrape_complete')).toBeInTheDocument();
    expect(screen.getByText('extraction_failed')).toBeInTheDocument();
  });

  it('renders log details text', () => {
    render(<ActivityLog initialLogs={sampleLogs} />);
    expect(screen.getByText('Scraped 10 pages from example.com')).toBeInTheDocument();
    expect(screen.getByText('Failed to parse PDF document')).toBeInTheDocument();
  });

  it('renders topic when present', () => {
    render(<ActivityLog initialLogs={sampleLogs} />);
    expect(screen.getByText('machine-learning')).toBeInTheDocument();
  });

  it('shows success and failure icons', () => {
    const { container } = render(<ActivityLog initialLogs={sampleLogs} />);
    // CheckCircle icons for success
    const checkIcons = container.querySelectorAll('.text-emerald-500');
    expect(checkIcons.length).toBeGreaterThan(0);
    // XCircle icons for failure
    const xIcons = container.querySelectorAll('.text-rose-500');
    expect(xIcons.length).toBeGreaterThan(0);
  });

  it('renders service emoji icons', () => {
    render(<ActivityLog initialLogs={sampleLogs} />);
    // Scraper emoji
    expect(screen.getByText('🕷️')).toBeInTheDocument();
    // Extractor emoji
    expect(screen.getByText('🔍')).toBeInTheDocument();
    // Knowledge emoji
    expect(screen.getByText('🧠')).toBeInTheDocument();
  });

  it('uses fallback emoji for unknown service', () => {
    const unknownLog: ActivityLogType[] = [{
      id: 'log-x',
      timestamp: '2024-01-01T00:00:00Z',
      service: 'unknown-service',
      action: 'test_action',
      details: 'Some details',
      topic: null,
      success: true,
    }];
    render(<ActivityLog initialLogs={unknownLog} />);
    expect(screen.getByText('⚙️')).toBeInTheDocument();
  });

  it('prepends a new log entry when a log_entry WS message arrives', () => {
    const wsLog: ActivityLogType = {
      id: 'ws-log-1',
      timestamp: '2024-01-01T12:00:00Z',
      service: 'reasoner',
      action: 'reasoning_complete',
      details: 'Reasoning done via WebSocket',
      topic: null,
      success: true,
    };

    // Capture the onMessage callback so we can call it after render
    let capturedOnMessage: OnMessageFn | undefined;
    useWebSocket.mockImplementation(({ onMessage }: UseWebSocketOptions): UseWebSocketReturn => {
      capturedOnMessage = onMessage;
      return { messages: [], isConnected: true, lastMessage: null, send: vi.fn() };
    });

    render(<ActivityLog initialLogs={[]} />);

    // Simulate a WS message arriving after render
    act(() => {
      capturedOnMessage?.({ type: 'log_entry', data: wsLog as unknown as Record<string, unknown>, timestamp: wsLog.timestamp });
    });

    expect(screen.getByText('Reasoning done via WebSocket')).toBeInTheDocument();
  });

  it('ignores WS messages that are not log_entry type', () => {
    let capturedOnMessage: OnMessageFn | undefined;
    useWebSocket.mockImplementation(({ onMessage }: UseWebSocketOptions): UseWebSocketReturn => {
      capturedOnMessage = onMessage;
      return { messages: [], isConnected: false, lastMessage: null, send: vi.fn() };
    });

    render(<ActivityLog initialLogs={[]} />);

    act(() => {
      capturedOnMessage?.({ type: 'status_update', data: {}, timestamp: '2024-01-01T00:00:00Z' });
    });

    expect(screen.getByText('No activity yet')).toBeInTheDocument();
  });
});
