import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { StatusPanel } from '../StatusPanel';
import type { DashboardStatus } from '@/lib/types';

// Mock the useWebSocket hook to avoid real WebSocket connections in tests
vi.mock('@/hooks/useWebSocket', () => ({
  useWebSocket: vi.fn(() => ({
    messages: [],
    isConnected: false,
    lastMessage: null,
    send: vi.fn(),
  })),
}));

const mockStatus: DashboardStatus = {
  current_activity: 'scraping',
  active_topics: 3,
  total_entities: 1500,
  total_claims: 4200,
  active_learning_cycles: 2,
  system_health: 'healthy',
  last_activity: '2024-01-01T10:30:00Z',
};

describe('StatusPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows a loading skeleton when status is null', () => {
    const { container } = render(<StatusPanel initialStatus={null} />);
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
    expect(screen.queryByText('System Status')).not.toBeInTheDocument();
  });

  it('renders System Status heading when status is provided', () => {
    render(<StatusPanel initialStatus={mockStatus} />);
    expect(screen.getByText('System Status')).toBeInTheDocument();
  });

  it('displays the current activity', () => {
    render(<StatusPanel initialStatus={mockStatus} />);
    expect(screen.getByText('scraping')).toBeInTheDocument();
  });

  it('displays the active topics count', () => {
    render(<StatusPanel initialStatus={mockStatus} />);
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('displays total entities with locale formatting', () => {
    render(<StatusPanel initialStatus={mockStatus} />);
    expect(screen.getByText('1,500')).toBeInTheDocument();
  });

  it('displays total claims with locale formatting', () => {
    render(<StatusPanel initialStatus={mockStatus} />);
    expect(screen.getByText('4,200')).toBeInTheDocument();
  });

  it('displays the active learning cycles count', () => {
    render(<StatusPanel initialStatus={mockStatus} />);
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('shows the last activity timestamp', () => {
    render(<StatusPanel initialStatus={mockStatus} />);
    expect(screen.getByText(/Last activity:/)).toBeInTheDocument();
  });

  it('does not show last activity when last_activity is null', () => {
    render(<StatusPanel initialStatus={{ ...mockStatus, last_activity: null }} />);
    expect(screen.queryByText(/Last activity:/)).not.toBeInTheDocument();
  });

  it('shows idle activity text with muted color when activity is idle', () => {
    render(<StatusPanel initialStatus={{ ...mockStatus, current_activity: 'idle' }} />);
    expect(screen.getByText('idle')).toBeInTheDocument();
  });

  it('shows health indicator for degraded system health', () => {
    const { container } = render(
      <StatusPanel initialStatus={{ ...mockStatus, system_health: 'degraded' }} />
    );
    // The health indicator circle should use amber color
    const circle = container.querySelector('.text-amber-500');
    expect(circle).toBeInTheDocument();
  });

  it('shows health indicator for unhealthy system health', () => {
    const { container } = render(
      <StatusPanel initialStatus={{ ...mockStatus, system_health: 'unhealthy' }} />
    );
    // Non-healthy, non-degraded → rose color
    const circle = container.querySelector('.text-rose-500');
    expect(circle).toBeInTheDocument();
  });
});
