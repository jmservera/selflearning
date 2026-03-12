import { useState, useEffect, useCallback } from 'react';
import { api } from '@/lib/api';
import type { TopicResponse, TopicDetail, TopicCreate, PriorityUpdate } from '@/lib/types';

interface UseTopicsReturn {
  topics: TopicResponse[];
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  createTopic: (data: TopicCreate) => Promise<TopicResponse>;
  getTopic: (topicId: string) => Promise<TopicDetail>;
  startLearning: (topicId: string) => Promise<void>;
  pauseTopic: (topicId: string) => Promise<void>;
  resumeTopic: (topicId: string) => Promise<void>;
  updatePriority: (topicId: string, priority: number) => Promise<void>;
}

export function useTopics(): UseTopicsReturn {
  const [topics, setTopics] = useState<TopicResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setError(null);
      const data = await api.topics.list();
      setTopics(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch topics';
      setError(message);
      console.error('Topics fetch error:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const createTopic = useCallback(async (data: TopicCreate): Promise<TopicResponse> => {
    const newTopic = await api.topics.create(data);
    await refresh();
    return newTopic;
  }, [refresh]);

  const getTopic = useCallback(async (topicId: string): Promise<TopicDetail> => {
    return await api.topics.get(topicId);
  }, []);

  const startLearning = useCallback(async (topicId: string): Promise<void> => {
    await api.topics.learn(topicId);
    await refresh();
  }, [refresh]);

  const pauseTopic = useCallback(async (topicId: string): Promise<void> => {
    await api.topics.pause(topicId);
    await refresh();
  }, [refresh]);

  const resumeTopic = useCallback(async (topicId: string): Promise<void> => {
    await api.topics.resume(topicId);
    await refresh();
  }, [refresh]);

  const updatePriority = useCallback(async (topicId: string, priority: number): Promise<void> => {
    const data: PriorityUpdate = { priority };
    await api.topics.updatePriority(topicId, data);
    await refresh();
  }, [refresh]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return {
    topics,
    isLoading,
    error,
    refresh,
    createTopic,
    getTopic,
    startLearning,
    pauseTopic,
    resumeTopic,
    updatePriority,
  };
}
