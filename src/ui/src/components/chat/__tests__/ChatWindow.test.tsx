import { render, screen } from '@testing-library/react';
import { describe, it, expect, beforeAll } from 'vitest';
import { ChatWindow } from '../ChatWindow';
import type { ChatResponse } from '@/lib/types';

// jsdom doesn't implement scrollIntoView
beforeAll(() => {
  window.HTMLElement.prototype.scrollIntoView = () => {};
});

const mockResponse: ChatResponse = {
  answer: 'Answer text',
  confidence: 0.8,
  sources: [],
  topic: 'ai',
  model: 'gpt-4',
  tokens_used: 50,
};

const messages = [
  {
    id: 'msg-1',
    role: 'user' as const,
    content: 'Hello AI',
    timestamp: new Date('2024-01-01T10:00:00'),
  },
  {
    id: 'msg-2',
    role: 'assistant' as const,
    content: 'Hello user',
    timestamp: new Date('2024-01-01T10:00:05'),
    response: mockResponse,
  },
];

describe('ChatWindow', () => {
  it('renders empty state when there are no messages and not loading', () => {
    render(<ChatWindow messages={[]} isLoading={false} />);
    expect(screen.getByText('Start a conversation')).toBeInTheDocument();
  });

  it('shows prompt examples in the empty state', () => {
    render(<ChatWindow messages={[]} isLoading={false} />);
    expect(screen.getByText(/quantum computing/)).toBeInTheDocument();
  });

  it('renders messages when provided', () => {
    render(<ChatWindow messages={messages} isLoading={false} />);
    expect(screen.getByText('Hello AI')).toBeInTheDocument();
    expect(screen.getByText('Hello user')).toBeInTheDocument();
  });

  it('does not show empty state when messages exist', () => {
    render(<ChatWindow messages={messages} isLoading={false} />);
    expect(screen.queryByText('Start a conversation')).not.toBeInTheDocument();
  });

  it('shows loading indicator when isLoading is true', () => {
    const { container } = render(<ChatWindow messages={[]} isLoading={true} />);
    expect(container.querySelector('.animate-spin')).toBeInTheDocument();
  });

  it('shows loading indicator even with existing messages', () => {
    const { container } = render(<ChatWindow messages={messages} isLoading={true} />);
    expect(container.querySelector('.animate-spin')).toBeInTheDocument();
  });

  it('hides loading indicator when isLoading is false', () => {
    const { container } = render(<ChatWindow messages={messages} isLoading={false} />);
    expect(container.querySelector('.animate-spin')).not.toBeInTheDocument();
  });

  it('does not show empty state when loading with no messages', () => {
    render(<ChatWindow messages={[]} isLoading={true} />);
    expect(screen.queryByText('Start a conversation')).not.toBeInTheDocument();
  });
});
