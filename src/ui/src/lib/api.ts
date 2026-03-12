import type {
  TopicCreate,
  TopicResponse,
  TopicDetail,
  PriorityUpdate,
  SearchResponse,
  ChatRequest,
  ChatResponse,
  SystemHealth,
  DashboardStatus,
  LearningProgress,
  ActivityLog,
  DecisionLog,
  Entity,
  KnowledgeGraph,
} from './types';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function fetchJson<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  
  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new ApiError(
        response.status,
        `API error (${response.status}): ${errorText || response.statusText}`
      );
    }

    return await response.json();
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new Error(`Network error: ${error instanceof Error ? error.message : 'Unknown error'}`);
  }
}

export const api = {
  health: {
    check: () => fetchJson<{ status: string }>('/health'),
    services: () => fetchJson<SystemHealth>('/health/services'),
  },

  topics: {
    list: () => fetchJson<TopicResponse[]>('/topics'),
    get: (topicId: string) => fetchJson<TopicDetail>(`/topics/${topicId}`),
    create: (data: TopicCreate) =>
      fetchJson<TopicResponse>('/topics', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    learn: (topicId: string) =>
      fetchJson<{ status: string; topic_id: string; message?: string }>(
        `/topics/${topicId}/learn`,
        { method: 'POST' }
      ),
    pause: (topicId: string) =>
      fetchJson<{ status: string; topic_id: string; message?: string }>(
        `/topics/${topicId}/pause`,
        { method: 'PUT' }
      ),
    resume: (topicId: string) =>
      fetchJson<{ status: string; topic_id: string; message?: string }>(
        `/topics/${topicId}/resume`,
        { method: 'PUT' }
      ),
    updatePriority: (topicId: string, data: PriorityUpdate) =>
      fetchJson<{ status: string }>(`/topics/${topicId}/priority`, {
        method: 'PUT',
        body: JSON.stringify(data),
      }),
  },

  knowledge: {
    search: (params: {
      q: string;
      topic?: string;
      doc_type?: string;
      min_confidence?: number;
      limit?: number;
      mode?: string;
    }) => {
      const query = new URLSearchParams();
      if (params.q) query.set('q', params.q);
      if (params.topic) query.set('topic', params.topic);
      if (params.doc_type) query.set('doc_type', params.doc_type);
      if (params.min_confidence !== undefined)
        query.set('min_confidence', params.min_confidence.toString());
      if (params.limit) query.set('limit', params.limit.toString());
      if (params.mode) query.set('mode', params.mode);
      
      return fetchJson<SearchResponse>(`/knowledge/search?${query}`);
    },
    getEntity: (entityId: string, topic?: string) => {
      const query = topic ? `?topic=${encodeURIComponent(topic)}` : '';
      return fetchJson<Entity>(`/knowledge/entities/${entityId}${query}`);
    },
    getGraph: (topic: string, limit = 100) =>
      fetchJson<KnowledgeGraph>(
        `/knowledge/topics/${encodeURIComponent(topic)}/graph?limit=${limit}`
      ),
  },

  dashboard: {
    status: () => fetchJson<DashboardStatus>('/dashboard/status'),
    progress: () => fetchJson<LearningProgress>('/dashboard/progress'),
    logs: (limit = 50) =>
      fetchJson<ActivityLog[]>(`/dashboard/logs?limit=${limit}`),
    decisions: (limit = 50) =>
      fetchJson<DecisionLog[]>(`/dashboard/decisions?limit=${limit}`),
  },

  chat: {
    send: (request: ChatRequest) =>
      fetchJson<ChatResponse>('/chat', {
        method: 'POST',
        body: JSON.stringify(request),
      }),
  },
};

export function getWebSocketUrl(path: string): string {
  const wsProtocol = API_BASE_URL.startsWith('https') ? 'wss' : 'ws';
  const wsHost = API_BASE_URL.replace(/^https?:\/\//, '');
  return `${wsProtocol}://${wsHost}${path}`;
}

export { ApiError };
