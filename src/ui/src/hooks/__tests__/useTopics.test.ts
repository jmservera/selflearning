import { renderHook, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useTopics } from '../useTopics';

vi.mock('@/lib/api', () => ({
  api: {
    topics: {
      list: vi.fn(),
      get: vi.fn(),
      create: vi.fn(),
      learn: vi.fn(),
      pause: vi.fn(),
      resume: vi.fn(),
      updatePriority: vi.fn(),
    },
  },
}));

import { api } from '@/lib/api';

const mockTopics = [
  {
    id: 'topic-1',
    name: 'Machine Learning',
    status: 'active' as const,
    priority: 5,
    current_expertise: 40,
    target_expertise: 100,
    entity_count: 200,
    claim_count: 500,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-02T00:00:00Z',
  },
];

describe('useTopics', () => {
  beforeEach(() => {
    vi.mocked(api.topics.list).mockResolvedValue(mockTopics);
    vi.mocked(api.topics.create).mockResolvedValue({
      id: 'topic-new',
      name: 'New Topic',
      status: 'pending',
      priority: 5,
      current_expertise: 0,
      target_expertise: 100,
      entity_count: 0,
      claim_count: 0,
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    });
    vi.mocked(api.topics.learn).mockResolvedValue({ status: 'started', topic_id: 'topic-1' });
    vi.mocked(api.topics.pause).mockResolvedValue({ status: 'paused', topic_id: 'topic-1' });
    vi.mocked(api.topics.resume).mockResolvedValue({ status: 'active', topic_id: 'topic-1' });
    vi.mocked(api.topics.updatePriority).mockResolvedValue({ status: 'updated' });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('starts with isLoading true', () => {
    const { result } = renderHook(() => useTopics());
    expect(result.current.isLoading).toBe(true);
  });

  it('fetches and populates topics on mount', async () => {
    const { result } = renderHook(() => useTopics());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.topics).toEqual(mockTopics);
  });

  it('sets error when list fails', async () => {
    vi.mocked(api.topics.list).mockRejectedValue(new Error('list failed'));
    const { result } = renderHook(() => useTopics());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.error).toBe('list failed');
  });

  it('creates a topic and refreshes the list', async () => {
    const { result } = renderHook(() => useTopics());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.createTopic({ name: 'New Topic' });
    });

    expect(api.topics.create).toHaveBeenCalledWith({ name: 'New Topic' });
    expect(api.topics.list).toHaveBeenCalledTimes(2); // initial + after create
  });

  it('calls startLearning and refreshes', async () => {
    const { result } = renderHook(() => useTopics());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.startLearning('topic-1');
    });

    expect(api.topics.learn).toHaveBeenCalledWith('topic-1');
    expect(api.topics.list).toHaveBeenCalledTimes(2);
  });

  it('calls pauseTopic and refreshes', async () => {
    const { result } = renderHook(() => useTopics());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.pauseTopic('topic-1');
    });

    expect(api.topics.pause).toHaveBeenCalledWith('topic-1');
  });

  it('calls resumeTopic and refreshes', async () => {
    const { result } = renderHook(() => useTopics());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.resumeTopic('topic-1');
    });

    expect(api.topics.resume).toHaveBeenCalledWith('topic-1');
  });

  it('calls updatePriority and refreshes', async () => {
    const { result } = renderHook(() => useTopics());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.updatePriority('topic-1', 8);
    });

    expect(api.topics.updatePriority).toHaveBeenCalledWith('topic-1', { priority: 8 });
  });

  it('calls getTopic by ID', async () => {
    const topicDetail = { ...mockTopics[0], seed_urls: [], tags: [], coverage_areas: [], avg_confidence: 0.8, relationship_count: 5, source_count: 10, learning_cycles_completed: 3, last_learning_cycle: null, gap_areas: [] };
    vi.mocked(api.topics.get).mockResolvedValue(topicDetail);

    const { result } = renderHook(() => useTopics());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    let detail;
    await act(async () => {
      detail = await result.current.getTopic('topic-1');
    });

    expect(api.topics.get).toHaveBeenCalledWith('topic-1');
    expect(detail).toEqual(topicDetail);
  });

  it('calls refresh to reload topics', async () => {
    const { result } = renderHook(() => useTopics());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.refresh();
    });

    expect(api.topics.list).toHaveBeenCalledTimes(2);
  });
});
