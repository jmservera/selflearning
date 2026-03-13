import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect } from 'vitest';
import { MessageBubble } from '../MessageBubble';
import type { ChatResponse } from '@/lib/types';

const userMessage = {
  id: 'msg-1',
  role: 'user' as const,
  content: 'What is machine learning?',
  timestamp: new Date('2024-01-01T10:00:00'),
};

const mockResponse: ChatResponse = {
  answer: 'Machine learning is a field of AI.',
  confidence: 0.9,
  sources: [
    {
      entity_id: 'e1',
      name: 'ML Fundamentals',
      source_url: 'https://example.com/ml',
      confidence: 0.9,
      snippet: 'Machine learning enables systems to learn from data.',
    },
  ],
  topic: 'machine-learning',
  model: 'gpt-4',
  tokens_used: 128,
};

const assistantMessage = {
  id: 'msg-2',
  role: 'assistant' as const,
  content: 'Machine learning is a field of AI.',
  timestamp: new Date('2024-01-01T10:00:05'),
  response: mockResponse,
};

describe('MessageBubble', () => {
  it('renders user message content', () => {
    render(<MessageBubble message={userMessage} />);
    expect(screen.getByText('What is machine learning?')).toBeInTheDocument();
  });

  it('renders assistant message content', () => {
    render(<MessageBubble message={assistantMessage} />);
    expect(screen.getByText('Machine learning is a field of AI.')).toBeInTheDocument();
  });

  it('shows model name for assistant messages', () => {
    render(<MessageBubble message={assistantMessage} />);
    expect(screen.getByText('gpt-4')).toBeInTheDocument();
  });

  it('shows token usage for assistant messages', () => {
    render(<MessageBubble message={assistantMessage} />);
    expect(screen.getByText('128 tokens')).toBeInTheDocument();
  });

  it('shows confidence for assistant messages', () => {
    render(<MessageBubble message={assistantMessage} />);
    expect(screen.getByText('90%')).toBeInTheDocument();
  });

  it('shows sources toggle for assistant messages with sources', () => {
    render(<MessageBubble message={assistantMessage} />);
    expect(screen.getByText('Sources (1)')).toBeInTheDocument();
  });

  it('expands sources when the toggle is clicked', async () => {
    const user = userEvent.setup();
    render(<MessageBubble message={assistantMessage} />);
    await user.click(screen.getByText('Sources (1)'));
    expect(screen.getByText('ML Fundamentals')).toBeInTheDocument();
  });

  it('collapses sources on second toggle click', async () => {
    const user = userEvent.setup();
    render(<MessageBubble message={assistantMessage} />);
    await user.click(screen.getByText('Sources (1)'));
    await user.click(screen.getByText('Sources (1)'));
    expect(screen.queryByText('ML Fundamentals')).not.toBeInTheDocument();
  });

  it('does not show model/tokens/sources for user messages', () => {
    render(<MessageBubble message={userMessage} />);
    expect(screen.queryByText('gpt-4')).not.toBeInTheDocument();
    expect(screen.queryByText(/tokens/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Sources/)).not.toBeInTheDocument();
  });

  it('renders assistant message without sources section when sources are empty', () => {
    const noSourcesMsg = {
      ...assistantMessage,
      response: { ...mockResponse, sources: [] },
    };
    render(<MessageBubble message={noSourcesMsg} />);
    expect(screen.queryByText(/Sources/)).not.toBeInTheDocument();
  });

  it('renders bold text for **markdown** in message content', () => {
    const boldMsg = {
      ...userMessage,
      content: 'Hello **world** here',
    };
    render(<MessageBubble message={boldMsg} />);
    const bold = screen.getByText('world');
    expect(bold.tagName).toBe('STRONG');
  });
});
