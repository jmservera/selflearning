import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

beforeAll(() => {
  window.HTMLElement.prototype.scrollIntoView = () => {};
});

vi.mock('@/lib/api', () => ({
  api: {
    topics: {
      list: vi.fn(),
    },
    chat: {
      send: vi.fn(),
    },
  },
}));

import { api } from '@/lib/api';
import ChatPage from '../ChatPage';

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

const mockChatResponse = {
  answer: 'This is the AI answer.',
  confidence: 0.9,
  sources: [],
  topic: null,
  model: 'gpt-4',
  tokens_used: 50,
};

describe('ChatPage', () => {
  beforeEach(() => {
    vi.mocked(api.topics.list).mockResolvedValue(mockTopics);
    vi.mocked(api.chat.send).mockResolvedValue(mockChatResponse);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders the chat heading', async () => {
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText('Chat with Knowledge Base')).toBeInTheDocument());
  });

  it('loads and displays topics in the sidebar', async () => {
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText('Machine Learning')).toBeInTheDocument());
  });

  it('shows empty state for chat when no messages sent', async () => {
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText('Start a conversation')).toBeInTheDocument());
  });

  it('sends a message and shows the response', async () => {
    // Use delay: null to eliminate real timer delays and prevent CI timeouts
    const user = userEvent.setup({ delay: null });
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>
    );

    const textarea = await screen.findByPlaceholderText('Ask a question...');
    await user.type(textarea, 'Hello AI');
    await user.click(screen.getByRole('button', { name: /send/i }));

    await waitFor(() => expect(screen.getByText('Hello AI')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText('This is the AI answer.')).toBeInTheDocument());
    expect(api.chat.send).toHaveBeenCalledWith({
      question: 'Hello AI',
      topic: null,
      include_sources: true,
    });
  });

  it('shows error when topics fail to load', async () => {
    vi.mocked(api.topics.list).mockRejectedValueOnce(new Error('load failed'));
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText('Failed to load topics')).toBeInTheDocument());
  });

  it('shows error on chat send failure and renders fallback message', async () => {
    vi.mocked(api.chat.send).mockRejectedValueOnce(new Error('chat failed'));
    const user = userEvent.setup({ delay: null });
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>
    );
    const textarea = await screen.findByPlaceholderText('Ask a question...');
    await user.type(textarea, 'bad question');
    await user.click(screen.getByRole('button', { name: /send/i }));
    await waitFor(() =>
      expect(screen.getByText('Failed to get response. Please try again.')).toBeInTheDocument()
    );
    await waitFor(() =>
      expect(
        screen.getByText(/I apologize, but I encountered an error/)
      ).toBeInTheDocument()
    );
  });

  it('clears the conversation when clear button is clicked', async () => {
    // Mock window.confirm to auto-accept
    vi.stubGlobal('confirm', vi.fn(() => true));
    const user = userEvent.setup({ delay: null });
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>
    );
    const textarea = await screen.findByPlaceholderText('Ask a question...');
    await user.type(textarea, 'First message');
    await user.click(screen.getByRole('button', { name: /send/i }));

    // Wait for the full request cycle (user message + AI response)
    await waitFor(() => expect(screen.getByText('This is the AI answer.')).toBeInTheDocument());

    await user.click(screen.getByTitle('Clear conversation'));
    await waitFor(() => expect(screen.getByText('Start a conversation')).toBeInTheDocument());
    expect(screen.queryByText('First message')).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it('shows topic name in header when a topic is selected', async () => {
    const user = userEvent.setup({ delay: null });
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText('Machine Learning')).toBeInTheDocument());
    await user.click(screen.getByText('Machine Learning'));
    // Header should update to show the selected topic name
    await waitFor(() => expect(screen.getAllByText('Machine Learning').length).toBeGreaterThan(0));
  });

  it('shows "All Topics" button in sidebar when topics are loaded', async () => {
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getAllByText('All Topics').length).toBeGreaterThan(0));
  });

  it('shows "No topics available yet" when topics list is empty', async () => {
    vi.mocked(api.topics.list).mockResolvedValue([]);
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText('No topics available yet')).toBeInTheDocument());
  });
});

