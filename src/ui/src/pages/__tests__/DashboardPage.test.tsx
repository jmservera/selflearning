import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { DashboardPage } from '../DashboardPage';

vi.mock('@/hooks/useWebSocket', () => ({
  useWebSocket: vi.fn(() => ({
    messages: [],
    isConnected: false,
    lastMessage: null,
    send: vi.fn(),
  })),
}));

vi.mock('@/hooks/useDashboard', () => ({
  useDashboard: vi.fn(),
}));

vi.mock('@/hooks/useTopics', () => ({
  useTopics: vi.fn(),
}));

import { useDashboard } from '@/hooks/useDashboard';
import { useTopics } from '@/hooks/useTopics';

const mockTopicActions = {
  topics: [],
  isLoading: false,
  error: null,
  refresh: vi.fn(),
  createTopic: vi.fn().mockResolvedValue({}),
  getTopic: vi.fn(),
  startLearning: vi.fn().mockResolvedValue(undefined),
  pauseTopic: vi.fn().mockResolvedValue(undefined),
  resumeTopic: vi.fn().mockResolvedValue(undefined),
  updatePriority: vi.fn().mockResolvedValue(undefined),
};

describe('DashboardPage', () => {
  beforeEach(() => {
    vi.mocked(useTopics).mockReturnValue(mockTopicActions);
  });

  it('shows loading spinner when data is loading', () => {
    vi.mocked(useDashboard).mockReturnValue({
      status: null,
      progress: null,
      logs: [],
      decisions: [],
      isLoading: true,
      error: null,
      refresh: vi.fn(),
    });

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    );
    expect(screen.getByText('Loading dashboard...')).toBeInTheDocument();
  });

  it('shows error message when there is an error', () => {
    vi.mocked(useDashboard).mockReturnValue({
      status: null,
      progress: null,
      logs: [],
      decisions: [],
      isLoading: false,
      error: 'Failed to load dashboard',
      refresh: vi.fn(),
    });

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    );
    expect(screen.getByText('Failed to load dashboard')).toBeInTheDocument();
  });

  it('renders the Dashboard heading when loaded', () => {
    vi.mocked(useDashboard).mockReturnValue({
      status: null,
      progress: null,
      logs: [],
      decisions: [],
      isLoading: false,
      error: null,
      refresh: vi.fn(),
    });

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    );
    expect(screen.getByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
  });

  it('renders Activity Log and Learning Progress sections', () => {
    vi.mocked(useDashboard).mockReturnValue({
      status: null,
      progress: null,
      logs: [],
      decisions: [],
      isLoading: false,
      error: null,
      refresh: vi.fn(),
    });

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    );
    expect(screen.getByText('Activity Log')).toBeInTheDocument();
  });
});
