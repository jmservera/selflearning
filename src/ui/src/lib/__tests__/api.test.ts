import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { api, getWebSocketUrl, ApiError } from '../api';

// Helper to create a mock Response object
function mockResponse(body: unknown, options: { status?: number; ok?: boolean } = {}) {
  const status = options.status ?? 200;
  const ok = options.ok ?? (status >= 200 && status < 300);
  return {
    ok,
    status,
    json: vi.fn().mockResolvedValue(body),
    text: vi.fn().mockResolvedValue(typeof body === 'string' ? body : JSON.stringify(body)),
    statusText: ok ? 'OK' : 'Error',
  } as unknown as Response;
}

describe('api', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe('health', () => {
    it('calls /health and returns status', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ status: 'ok' }));
      const result = await api.health.check();
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/health'),
        expect.objectContaining({ headers: expect.objectContaining({ 'Content-Type': 'application/json' }) })
      );
      expect(result).toEqual({ status: 'ok' });
    });

    it('calls /health/services and returns system health', async () => {
      const mockHealth = { status: 'healthy', services: [], timestamp: '2024-01-01T00:00:00Z' };
      vi.mocked(fetch).mockResolvedValueOnce(mockResponse(mockHealth));
      const result = await api.health.services();
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/health/services'),
        expect.any(Object)
      );
      expect(result).toEqual(mockHealth);
    });
  });

  describe('topics', () => {
    it('lists topics via GET /topics', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(mockResponse([]));
      await api.topics.list();
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/topics'),
        expect.objectContaining({ headers: expect.any(Object) })
      );
    });

    it('creates a topic via POST /topics', async () => {
      const newTopic = { name: 'AI Ethics', priority: 7 };
      vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ id: 't1', ...newTopic }));
      await api.topics.create(newTopic);
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/topics'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(newTopic),
        })
      );
    });

    it('triggers learning via POST /topics/:id/learn', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ status: 'started', topic_id: 't1' }));
      await api.topics.learn('t1');
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/topics/t1/learn'),
        expect.objectContaining({ method: 'POST' })
      );
    });

    it('pauses topic via PUT /topics/:id/pause', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ status: 'paused', topic_id: 't1' }));
      await api.topics.pause('t1');
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/topics/t1/pause'),
        expect.objectContaining({ method: 'PUT' })
      );
    });

    it('resumes topic via PUT /topics/:id/resume', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ status: 'active', topic_id: 't1' }));
      await api.topics.resume('t1');
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/topics/t1/resume'),
        expect.objectContaining({ method: 'PUT' })
      );
    });

    it('updates priority via PUT /topics/:id/priority', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ status: 'updated' }));
      await api.topics.updatePriority('t1', { priority: 8 });
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/topics/t1/priority'),
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({ priority: 8 }),
        })
      );
    });
  });

  describe('knowledge', () => {
    it('searches knowledge with all optional params', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ items: [], total_count: 0, facets: {} }));
      await api.knowledge.search({
        q: 'ml',
        topic: 'ai',
        doc_type: 'entity',
        min_confidence: 0.7,
        limit: 20,
        mode: 'semantic',
      });
      const calledUrl = vi.mocked(fetch).mock.calls[0][0] as string;
      expect(calledUrl).toContain('doc_type=entity');
      expect(calledUrl).toContain('min_confidence=0.7');
      expect(calledUrl).toContain('mode=semantic');
    });

    it('searches knowledge with only required q param (no optional params)', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ items: [], total_count: 0, facets: {} }));
      await api.knowledge.search({ q: 'test' });
      const calledUrl = vi.mocked(fetch).mock.calls[0][0] as string;
      expect(calledUrl).toContain('q=test');
      // No optional params in URL
      expect(calledUrl).not.toContain('topic=');
      expect(calledUrl).not.toContain('doc_type=');
    });

    it('searches knowledge with query params', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ items: [], total_count: 0, facets: {} }));
      await api.knowledge.search({ q: 'neural network', topic: 'ml', limit: 10 });
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/knowledge/search?'),
        expect.any(Object)
      );
      const calledUrl = vi.mocked(fetch).mock.calls[0][0] as string;
      expect(calledUrl).toContain('q=neural+network');
      expect(calledUrl).toContain('topic=ml');
      expect(calledUrl).toContain('limit=10');
    });

    it('fetches entity by id', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ id: 'e1', name: 'Neuron' }));
      await api.knowledge.getEntity('e1');
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/knowledge/entities/e1'),
        expect.any(Object)
      );
    });

    it('fetches entity with topic query param', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ id: 'e1', name: 'Neuron' }));
      await api.knowledge.getEntity('e1', 'ml');
      const calledUrl = vi.mocked(fetch).mock.calls[0][0] as string;
      expect(calledUrl).toContain('?topic=ml');
    });

    it('fetches knowledge graph', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(
        mockResponse({ entities: [], relationships: [], topic: 'ml' })
      );
      await api.knowledge.getGraph('ml', 50);
      const calledUrl = vi.mocked(fetch).mock.calls[0][0] as string;
      expect(calledUrl).toContain('/knowledge/topics/ml/graph');
      expect(calledUrl).toContain('limit=50');
    });
  });

  describe('dashboard', () => {
    it('fetches dashboard status', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ current_activity: 'idle' }));
      await api.dashboard.status();
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/dashboard/status'),
        expect.any(Object)
      );
    });

    it('fetches learning progress', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ topics: [] }));
      await api.dashboard.progress();
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/dashboard/progress'),
        expect.any(Object)
      );
    });

    it('fetches activity logs with default limit', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(mockResponse([]));
      await api.dashboard.logs();
      const calledUrl = vi.mocked(fetch).mock.calls[0][0] as string;
      expect(calledUrl).toContain('/dashboard/logs?limit=50');
    });

    it('fetches decision logs with custom limit', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(mockResponse([]));
      await api.dashboard.decisions(10);
      const calledUrl = vi.mocked(fetch).mock.calls[0][0] as string;
      expect(calledUrl).toContain('/dashboard/decisions?limit=10');
    });
  });

  describe('chat', () => {
    it('sends a chat message via POST /chat', async () => {
      const request = { question: 'What is AI?', topic: 'ai' };
      vi.mocked(fetch).mockResolvedValueOnce(
        mockResponse({ answer: 'AI is...', confidence: 0.9, sources: [], topic: 'ai', model: 'gpt-4', tokens_used: 50 })
      );
      await api.chat.send(request);
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/chat'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(request),
        })
      );
    });
  });

  describe('error handling', () => {
    it('throws ApiError on non-ok response', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(mockResponse('Not Found', { status: 404, ok: false }));
      await expect(api.health.check()).rejects.toThrow(ApiError);
    });

    it('throws ApiError with correct status code', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(mockResponse('Server Error', { status: 500, ok: false }));
      try {
        await api.health.check();
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError);
        expect((err as ApiError).status).toBe(500);
      }
    });

    it('throws a generic error on network failure', async () => {
      vi.mocked(fetch).mockRejectedValueOnce(new Error('Network failure'));
      await expect(api.health.check()).rejects.toThrow('Network error: Network failure');
    });
  });
});

describe('getWebSocketUrl', () => {
  it('generates ws:// URL for http base URL', () => {
    const url = getWebSocketUrl('/ws/status');
    expect(url).toMatch(/^ws:\/\//);
    expect(url).toContain('/ws/status');
  });
});
