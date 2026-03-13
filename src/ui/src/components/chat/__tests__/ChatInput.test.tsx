import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { ChatInput } from '../ChatInput';
import type { TopicResponse } from '@/lib/types';

const mockTopics: TopicResponse[] = [
  {
    id: 'topic-1',
    name: 'Machine Learning',
    status: 'active',
    priority: 5,
    current_expertise: 40,
    target_expertise: 100,
    entity_count: 200,
    claim_count: 500,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-02T00:00:00Z',
  },
  {
    id: 'topic-2',
    name: 'Deep Learning',
    status: 'paused',
    priority: 3,
    current_expertise: 20,
    target_expertise: 100,
    entity_count: 80,
    claim_count: 150,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-02T00:00:00Z',
  },
];

describe('ChatInput', () => {
  const defaultProps = {
    onSendMessage: vi.fn(),
    onClearConversation: vi.fn(),
    isLoading: false,
    topics: mockTopics,
    onTopicChange: vi.fn(),
  };

  it('renders the textarea and send button', () => {
    render(<ChatInput {...defaultProps} />);
    expect(screen.getByPlaceholderText('Ask a question...')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /send/i })).toBeInTheDocument();
  });

  it('disables send button when textarea is empty', () => {
    render(<ChatInput {...defaultProps} />);
    expect(screen.getByRole('button', { name: /send/i })).toBeDisabled();
  });

  it('enables send button when text is entered', async () => {
    const user = userEvent.setup();
    render(<ChatInput {...defaultProps} />);
    await user.type(screen.getByPlaceholderText('Ask a question...'), 'Hello');
    expect(screen.getByRole('button', { name: /send/i })).toBeEnabled();
  });

  it('calls onSendMessage when form is submitted', async () => {
    const onSendMessage = vi.fn();
    const user = userEvent.setup();
    render(<ChatInput {...defaultProps} onSendMessage={onSendMessage} />);
    await user.type(screen.getByPlaceholderText('Ask a question...'), 'Hello AI');
    await user.click(screen.getByRole('button', { name: /send/i }));
    expect(onSendMessage).toHaveBeenCalledWith('Hello AI', undefined);
  });

  it('clears the textarea after sending', async () => {
    const user = userEvent.setup();
    render(<ChatInput {...defaultProps} />);
    const textarea = screen.getByPlaceholderText('Ask a question...');
    await user.type(textarea, 'Hello');
    await user.click(screen.getByRole('button', { name: /send/i }));
    expect(textarea).toHaveValue('');
  });

  it('sends message on Enter key press', async () => {
    const onSendMessage = vi.fn();
    const user = userEvent.setup();
    render(<ChatInput {...defaultProps} onSendMessage={onSendMessage} />);
    const textarea = screen.getByPlaceholderText('Ask a question...');
    await user.type(textarea, 'Hello{Enter}');
    expect(onSendMessage).toHaveBeenCalledWith('Hello', undefined);
  });

  it('does not send on Shift+Enter', async () => {
    const onSendMessage = vi.fn();
    const user = userEvent.setup();
    render(<ChatInput {...defaultProps} onSendMessage={onSendMessage} />);
    const textarea = screen.getByPlaceholderText('Ask a question...');
    await user.type(textarea, 'Line1{Shift>}{Enter}{/Shift}Line2');
    expect(onSendMessage).not.toHaveBeenCalled();
  });

  it('disables textarea and send button while loading', () => {
    render(<ChatInput {...defaultProps} isLoading={true} />);
    expect(screen.getByPlaceholderText('Ask a question...')).toBeDisabled();
    expect(screen.getByRole('button', { name: /send/i })).toBeDisabled();
  });

  it('calls onClearConversation when trash button is clicked', async () => {
    const onClearConversation = vi.fn();
    const user = userEvent.setup();
    render(<ChatInput {...defaultProps} onClearConversation={onClearConversation} />);
    await user.click(screen.getByTitle('Clear conversation'));
    expect(onClearConversation).toHaveBeenCalledTimes(1);
  });

  it('shows topic filter dropdown when filter button is clicked', async () => {
    const user = userEvent.setup();
    render(<ChatInput {...defaultProps} />);
    await user.click(screen.getByRole('button', { name: /all topics/i }));
    expect(screen.getByText('Machine Learning')).toBeInTheDocument();
    expect(screen.getByText('Deep Learning')).toBeInTheDocument();
  });

  it('calls onTopicChange when a topic is selected', async () => {
    const onTopicChange = vi.fn();
    const user = userEvent.setup();
    render(<ChatInput {...defaultProps} onTopicChange={onTopicChange} />);
    await user.click(screen.getByRole('button', { name: /all topics/i }));
    await user.click(screen.getByText('Machine Learning'));
    expect(onTopicChange).toHaveBeenCalledWith('topic-1');
  });

  it('shows selected topic name when a topic is active', () => {
    render(<ChatInput {...defaultProps} selectedTopic="topic-1" />);
    expect(screen.getByRole('button', { name: /machine learning/i })).toBeInTheDocument();
  });

  it('calls onSendMessage with selected topic id', async () => {
    const onSendMessage = vi.fn();
    const user = userEvent.setup();
    render(
      <ChatInput {...defaultProps} onSendMessage={onSendMessage} selectedTopic="topic-2" />
    );
    await user.type(screen.getByPlaceholderText('Ask a question...'), 'Tell me more');
    await user.click(screen.getByRole('button', { name: /send/i }));
    expect(onSendMessage).toHaveBeenCalledWith('Tell me more', 'topic-2');
  });
});
