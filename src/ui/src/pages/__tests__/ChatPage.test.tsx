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

// ChatPage is a default export
const ChatPage = (await import('../ChatPage')).default;

describe('ChatPage', () => {
  beforeEach(() => {
    vi.mocked(api.topics.list).mockResolvedValue(mockTopics);
    vi.mocked(api.chat.send).mockResolvedValue({
      answer: 'This is the AI answer.',
      confidence: 0.9,
      sources: [],
      topic: null,
      model: 'gpt-4',
      tokens_used: 50,
    });
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
    await waitFor(() => screen.getByText('Start a conversation'));
    expect(screen.getByText('Start a conversation')).toBeInTheDocument();
  });

  it('sends a message and shows the response', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>
    );
    await waitFor(() => screen.getByPlaceholderText('Ask a question...'));

    await user.type(screen.getByPlaceholderText('Ask a question...'), 'Hello AI');
    await user.click(screen.getByRole('button', { name: /send/i }));

    await waitFor(() => screen.getByText('Hello AI'));
    expect(screen.getByText('Hello AI')).toBeInTheDocument();

    await waitFor(() => screen.getByText('This is the AI answer.'));
    expect(screen.getByText('This is the AI answer.')).toBeInTheDocument();
  });

  it('shows error when topics fail to load', async () => {
    vi.mocked(api.topics.list).mockRejectedValueOnce(new Error('load failed'));
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>
    );
    await waitFor(() => screen.getByText('Failed to load topics'));
    expect(screen.getByText('Failed to load topics')).toBeInTheDocument();
  });

  it('shows error on chat send failure', async () => {
    vi.mocked(api.chat.send).mockRejectedValueOnce(new Error('chat failed'));
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>
    );
    await waitFor(() => screen.getByPlaceholderText('Ask a question...'));
    await user.type(screen.getByPlaceholderText('Ask a question...'), 'bad question');
    await user.click(screen.getByRole('button', { name: /send/i }));
    await waitFor(() => screen.getByText('Failed to get response. Please try again.'));
    expect(screen.getByText('Failed to get response. Please try again.')).toBeInTheDocument();
  });
});
