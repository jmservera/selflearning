import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

beforeAll(() => {
  window.HTMLElement.prototype.scrollIntoView = () => {};
  // jsdom doesn't implement getBoundingClientRect properly for SVG containers
  window.SVGElement.prototype.getBoundingClientRect = () => ({
    width: 800,
    height: 600,
    top: 0,
    left: 0,
    bottom: 600,
    right: 800,
    x: 0,
    y: 0,
    toJSON: () => {},
  });
});

vi.mock('@/lib/api', () => ({
  api: {
    topics: {
      list: vi.fn(),
      get: vi.fn(),
    },
    knowledge: {
      getGraph: vi.fn(),
      search: vi.fn(),
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

const mockTopicDetail = {
  ...mockTopics[0],
  description: 'ML description',
  seed_urls: [],
  tags: [],
  coverage_areas: ['Supervised Learning'],
  avg_confidence: 0.8,
  relationship_count: 10,
  source_count: 20,
  learning_cycles_completed: 3,
  last_learning_cycle: null,
  gap_areas: ['Reinforcement Learning'],
};

const mockGraph = { entities: [], relationships: [], topic: 'topic-1' };

const KnowledgeExplorerPage = (await import('../KnowledgeExplorerPage')).default;

describe('KnowledgeExplorerPage', () => {
  beforeEach(() => {
    vi.mocked(api.topics.list).mockResolvedValue(mockTopics);
    vi.mocked(api.topics.get).mockResolvedValue(mockTopicDetail);
    vi.mocked(api.knowledge.getGraph).mockResolvedValue(mockGraph);
    vi.mocked(api.knowledge.search).mockResolvedValue({
      items: [],
      total_count: 0,
      facets: {},
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders the knowledge explorer page with topic list', async () => {
    render(
      <MemoryRouter>
        <KnowledgeExplorerPage />
      </MemoryRouter>
    );
    await waitFor(() => screen.getByText('Machine Learning'));
    expect(screen.getByText('Machine Learning')).toBeInTheDocument();
  });

  it('loads topic detail when a topic is selected', async () => {
    render(
      <MemoryRouter>
        <KnowledgeExplorerPage />
      </MemoryRouter>
    );
    await waitFor(() => expect(api.topics.get).toHaveBeenCalledWith('topic-1'));
  });

  it('shows TopicSummary after loading topic detail', async () => {
    render(
      <MemoryRouter>
        <KnowledgeExplorerPage />
      </MemoryRouter>
    );
    // TopicSummary renders the avg_confidence value
    await waitFor(() => screen.getByText('80%'));
    expect(screen.getByText('80%')).toBeInTheDocument();
  });

  it('shows GapAnalysis section', async () => {
    render(
      <MemoryRouter>
        <KnowledgeExplorerPage />
      </MemoryRouter>
    );
    await waitFor(() => screen.getByText('Knowledge Gaps'));
    expect(screen.getByText('Knowledge Gaps')).toBeInTheDocument();
  });

  it('renders search input', async () => {
    render(
      <MemoryRouter>
        <KnowledgeExplorerPage />
      </MemoryRouter>
    );
    await waitFor(() => screen.getByPlaceholderText('Search entities, claims, or relationships...'));
    expect(screen.getByPlaceholderText('Search entities, claims, or relationships...')).toBeInTheDocument();
  });

  it('shows error when topics fail to load', async () => {
    vi.mocked(api.topics.list).mockRejectedValueOnce(new Error('Failed'));
    render(
      <MemoryRouter>
        <KnowledgeExplorerPage />
      </MemoryRouter>
    );
    await waitFor(() => screen.getByText('Failed to load topics'));
    expect(screen.getByText('Failed to load topics')).toBeInTheDocument();
  });

  it('selects a different topic via the dropdown', async () => {
    const moreMockTopics = [
      ...mockTopics,
      {
        id: 'topic-2',
        name: 'Deep Learning',
        status: 'paused' as const,
        priority: 3,
        current_expertise: 20,
        target_expertise: 100,
        entity_count: 50,
        claim_count: 100,
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-02T00:00:00Z',
      },
    ];
    vi.mocked(api.topics.list).mockResolvedValue(moreMockTopics);

    const user = userEvent.setup({ delay: null });
    render(
      <MemoryRouter>
        <KnowledgeExplorerPage />
      </MemoryRouter>
    );

    await waitFor(() => screen.getByText('Deep Learning'));
    await user.selectOptions(screen.getByRole('combobox'), 'topic-2');
    await waitFor(() =>
      expect(api.topics.get).toHaveBeenCalledWith('topic-2')
    );
  });

  it('shows error when topic data fails to load', async () => {
    vi.mocked(api.topics.get).mockRejectedValueOnce(new Error('topic load failed'));
    render(
      <MemoryRouter>
        <KnowledgeExplorerPage />
      </MemoryRouter>
    );
    await waitFor(() => screen.getByText('Failed to load topic data'));
    expect(screen.getByText('Failed to load topic data')).toBeInTheDocument();
  });

  it('performs a search and shows search error on failure', async () => {
    vi.mocked(api.knowledge.search).mockRejectedValueOnce(new Error('search failed'));
    const user = userEvent.setup({ delay: null });
    render(
      <MemoryRouter>
        <KnowledgeExplorerPage />
      </MemoryRouter>
    );
    await waitFor(() => screen.getByPlaceholderText('Search entities, claims, or relationships...'));
    const searchInput = screen.getByPlaceholderText('Search entities, claims, or relationships...');
    await user.type(searchInput, 'neural');
    await user.keyboard('{Enter}');
    await waitFor(() => screen.getByText('Search failed'));
    expect(screen.getByText('Search failed')).toBeInTheDocument();
  });

  it('shows empty state when no topics are loaded', async () => {
    vi.mocked(api.topics.list).mockResolvedValue([]);
    render(
      <MemoryRouter>
        <KnowledgeExplorerPage />
      </MemoryRouter>
    );
    await waitFor(() => screen.getByText('Knowledge Explorer'));
    expect(screen.getByText('Knowledge Explorer')).toBeInTheDocument();
  });

  it('performs a successful search with entity results', async () => {
    // Load entities in the graph so search can find them
    const graphWithEntities = {
      entities: [
        {
          id: 'e1',
          name: 'Neural Network',
          entity_type: 'concept',
          confidence: 0.9,
          description: '',
          topic: 'ml',
          source_urls: [],
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
        },
      ],
      relationships: [],
      topic: 'topic-1',
    };
    vi.mocked(api.knowledge.getGraph).mockResolvedValue(graphWithEntities);
    vi.mocked(api.knowledge.search).mockResolvedValue({
      items: [{
        id: 'e1',
        doc_type: 'entity',
        name: 'Neural Network',
        statement: '',
        topic: 'ml',
        confidence: 0.9,
        score: 0.9,
        highlights: {},
      }],
      total_count: 1,
      facets: {},
    });

    const user = userEvent.setup({ delay: null });
    render(
      <MemoryRouter>
        <KnowledgeExplorerPage />
      </MemoryRouter>
    );
    await waitFor(() => screen.getByPlaceholderText('Search entities, claims, or relationships...'));
    const searchInput = screen.getByPlaceholderText('Search entities, claims, or relationships...');
    await user.type(searchInput, 'neural');
    await user.keyboard('{Enter}');
    await waitFor(() => expect(api.knowledge.search).toHaveBeenCalled());
  });
});
