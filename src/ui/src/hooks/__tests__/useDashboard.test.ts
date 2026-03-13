import { renderHook, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useDashboard } from '../useDashboard';

vi.mock('@/lib/api', () => ({
  api: {
    dashboard: {
      status: vi.fn(),
      progress: vi.fn(),
      logs: vi.fn(),
      decisions: vi.fn(),
    },
  },
}));

import { api } from '@/lib/api';

const mockStatus = {
  current_activity: 'idle',
  active_topics: 2,
  total_entities: 500,
  total_claims: 1200,
  active_learning_cycles: 0,
  system_health: 'healthy',
  last_activity: null,
};

const mockProgress = {
  topics: [],
  overall_expertise: 0.3,
  total_entities: 500,
  total_claims: 1200,
  total_sources: 50,
  learning_rate: 5.0,
};

describe('useDashboard', () => {
  beforeEach(() => {
    vi.mocked(api.dashboard.status).mockResolvedValue(mockStatus);
    vi.mocked(api.dashboard.progress).mockResolvedValue(mockProgress);
    vi.mocked(api.dashboard.logs).mockResolvedValue([]);
    vi.mocked(api.dashboard.decisions).mockResolvedValue([]);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('starts with isLoading true', () => {
    const { result } = renderHook(() => useDashboard(0));
    expect(result.current.isLoading).toBe(true);
  });

  it('fetches and populates status and progress', async () => {
    const { result } = renderHook(() => useDashboard(0));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.status).toEqual(mockStatus);
    expect(result.current.progress).toEqual(mockProgress);
  });

  it('sets error when API call fails', async () => {
    vi.mocked(api.dashboard.status).mockRejectedValue(new Error('Network error'));
    const { result } = renderHook(() => useDashboard(0));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.error).toBe('Network error');
  });

  it('calls refresh to reload data', async () => {
    const { result } = renderHook(() => useDashboard(0));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const callsBefore = vi.mocked(api.dashboard.status).mock.calls.length;
    await act(async () => {
      await result.current.refresh();
    });
    expect(vi.mocked(api.dashboard.status).mock.calls.length).toBeGreaterThan(callsBefore);
  });

  it('clears error on successful refresh after failure', async () => {
    vi.mocked(api.dashboard.status).mockRejectedValueOnce(new Error('fail'));
    const { result } = renderHook(() => useDashboard(0));
    await waitFor(() => expect(result.current.error).toBe('fail'));

    vi.mocked(api.dashboard.status).mockResolvedValueOnce(mockStatus);
    await act(async () => {
      await result.current.refresh();
    });
    expect(result.current.error).toBeNull();
  });

  it('starts auto-refresh when autoRefreshMs > 0', async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useDashboard(1000));
    await act(async () => {
      await Promise.resolve();
    });
    const callsAfterMount = vi.mocked(api.dashboard.status).mock.calls.length;
    vi.advanceTimersByTime(1000);
    await act(async () => {
      await Promise.resolve();
    });
    expect(vi.mocked(api.dashboard.status).mock.calls.length).toBeGreaterThan(callsAfterMount);
    vi.useRealTimers();
    result.current; // keep reference alive
  });
});
