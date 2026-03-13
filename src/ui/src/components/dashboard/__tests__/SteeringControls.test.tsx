import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { SteeringControls } from '../SteeringControls';
import type { TopicResponse, TopicCreate } from '@/lib/types';

const mockCreatedTopic: TopicResponse = {
  id: 'new-topic',
  name: 'Quantum Computing',
  status: 'pending',
  priority: 5,
  current_expertise: 0,
  target_expertise: 80,
  entity_count: 0,
  claim_count: 0,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
};

describe('SteeringControls', () => {
  // vi.fn() typed mock – cast when passing to component props
  const onCreateTopicMock = vi.fn().mockResolvedValue(mockCreatedTopic);

  beforeEach(() => {
    onCreateTopicMock.mockClear();
    onCreateTopicMock.mockResolvedValue(mockCreatedTopic);
  });

  it('renders the Steering Controls heading', () => {
    render(<SteeringControls onCreateTopic={onCreateTopicMock as unknown as (data: TopicCreate) => Promise<TopicResponse>} />);
    expect(screen.getByText('Steering Controls')).toBeInTheDocument();
  });

  it('renders the New Topic button', () => {
    render(<SteeringControls onCreateTopic={onCreateTopicMock as unknown as (data: TopicCreate) => Promise<TopicResponse>} />);
    expect(screen.getByRole('button', { name: /new topic/i })).toBeInTheDocument();
  });

  it('shows the empty placeholder when form is closed', () => {
    render(<SteeringControls onCreateTopic={onCreateTopicMock as unknown as (data: TopicCreate) => Promise<TopicResponse>} />);
    expect(screen.getByText('Create a new topic to start learning')).toBeInTheDocument();
  });

  it('opens the form when New Topic is clicked', async () => {
    const user = userEvent.setup({ delay: null });
    render(<SteeringControls onCreateTopic={onCreateTopicMock as unknown as (data: TopicCreate) => Promise<TopicResponse>} />);
    await user.click(screen.getByRole('button', { name: /new topic/i }));
    expect(screen.getByPlaceholderText('e.g., Quantum Computing')).toBeInTheDocument();
  });

  it('closes the form when Cancel is clicked', async () => {
    const user = userEvent.setup({ delay: null });
    render(<SteeringControls onCreateTopic={onCreateTopicMock as unknown as (data: TopicCreate) => Promise<TopicResponse>} />);
    await user.click(screen.getByRole('button', { name: /new topic/i }));
    expect(screen.getByPlaceholderText('e.g., Quantum Computing')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /cancel/i }));
    expect(screen.queryByPlaceholderText('e.g., Quantum Computing')).not.toBeInTheDocument();
    expect(screen.getByText('Create a new topic to start learning')).toBeInTheDocument();
  });

  it('requires the Topic Name field before submitting', async () => {
    const user = userEvent.setup({ delay: null });
    render(<SteeringControls onCreateTopic={onCreateTopicMock as unknown as (data: TopicCreate) => Promise<TopicResponse>} />);
    await user.click(screen.getByRole('button', { name: /new topic/i }));
    expect(screen.getByRole('button', { name: /create topic/i })).toBeDisabled();
  });

  it('enables Create Topic button after entering a topic name', async () => {
    const user = userEvent.setup({ delay: null });
    render(<SteeringControls onCreateTopic={onCreateTopicMock as unknown as (data: TopicCreate) => Promise<TopicResponse>} />);
    await user.click(screen.getByRole('button', { name: /new topic/i }));
    await user.type(screen.getByPlaceholderText('e.g., Quantum Computing'), 'AI Ethics');
    expect(screen.getByRole('button', { name: /create topic/i })).toBeEnabled();
  });

  it('calls onCreateTopic with the correct data on submit', async () => {
    const user = userEvent.setup({ delay: null });
    render(<SteeringControls onCreateTopic={onCreateTopicMock as unknown as (data: TopicCreate) => Promise<TopicResponse>} />);
    await user.click(screen.getByRole('button', { name: /new topic/i }));

    await user.type(screen.getByPlaceholderText('e.g., Quantum Computing'), 'AI Ethics');
    await user.type(
      screen.getByPlaceholderText('Brief description of what to learn...'),
      'Ethical AI research'
    );
    await user.click(screen.getByRole('button', { name: /create topic/i }));

    await waitFor(() => expect(onCreateTopicMock).toHaveBeenCalledTimes(1));
    const callArg = onCreateTopicMock.mock.calls[0][0];
    expect(callArg.name).toBe('AI Ethics');
    expect(callArg.description).toBe('Ethical AI research');
    expect(callArg.seed_urls).toEqual([]);
    expect(callArg.tags).toEqual([]);
  });

  it('closes the form and resets fields after successful submission', async () => {
    const user = userEvent.setup({ delay: null });
    render(<SteeringControls onCreateTopic={onCreateTopicMock as unknown as (data: TopicCreate) => Promise<TopicResponse>} />);
    await user.click(screen.getByRole('button', { name: /new topic/i }));
    await user.type(screen.getByPlaceholderText('e.g., Quantum Computing'), 'AI Ethics');
    await user.click(screen.getByRole('button', { name: /create topic/i }));

    await waitFor(() =>
      expect(screen.queryByPlaceholderText('e.g., Quantum Computing')).not.toBeInTheDocument()
    );
    expect(screen.getByText('Create a new topic to start learning')).toBeInTheDocument();
  });

  it('filters out empty seed URLs before submitting', async () => {
    const user = userEvent.setup({ delay: null });
    render(<SteeringControls onCreateTopic={onCreateTopicMock as unknown as (data: TopicCreate) => Promise<TopicResponse>} />);
    await user.click(screen.getByRole('button', { name: /new topic/i }));
    await user.type(screen.getByPlaceholderText('e.g., Quantum Computing'), 'Test Topic');
    const seedUrlsTextarea = screen.getByPlaceholderText(
      /https:\/\/example\.com\/article1/
    );
    await user.type(seedUrlsTextarea, 'https://example.com/a');
    // Clear and leave empty line
    await user.clear(seedUrlsTextarea);
    await user.type(seedUrlsTextarea, '   ');
    await user.click(screen.getByRole('button', { name: /create topic/i }));

    await waitFor(() => expect(onCreateTopicMock).toHaveBeenCalledTimes(1));
    const callArg = onCreateTopicMock.mock.calls[0][0];
    expect(callArg.seed_urls).toEqual([]);
  });

  it('handles comma-separated tags correctly', async () => {
    const user = userEvent.setup({ delay: null });
    render(<SteeringControls onCreateTopic={onCreateTopicMock as unknown as (data: TopicCreate) => Promise<TopicResponse>} />);
    await user.click(screen.getByRole('button', { name: /new topic/i }));
    await user.type(screen.getByPlaceholderText('e.g., Quantum Computing'), 'Test Topic');
    await user.type(
      screen.getByPlaceholderText('physics, technology, research'),
      'ai, ethics, technology'
    );
    await user.click(screen.getByRole('button', { name: /create topic/i }));

    await waitFor(() => expect(onCreateTopicMock).toHaveBeenCalledTimes(1));
    const callArg = onCreateTopicMock.mock.calls[0][0];
    expect(callArg.tags).toEqual(['ai', 'ethics', 'technology']);
  });

  it('shows submitting state while creating', async () => {
    let resolveCreate!: (v: TopicResponse) => void;
    const slowCreate: (data: TopicCreate) => Promise<TopicResponse> = vi.fn(
      () => new Promise<TopicResponse>((res) => { resolveCreate = res; })
    );
    const user = userEvent.setup({ delay: null });
    render(<SteeringControls onCreateTopic={slowCreate} />);
    await user.click(screen.getByRole('button', { name: /new topic/i }));
    await user.type(screen.getByPlaceholderText('e.g., Quantum Computing'), 'Test');
    await user.click(screen.getByRole('button', { name: /create topic/i }));

    // While pending, button shows "Creating..."
    expect(screen.getByText('Creating...')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /cancel/i })).toBeDisabled();

    // Resolve the promise
    resolveCreate(mockCreatedTopic);
    await waitFor(() =>
      expect(screen.queryByText('Creating...')).not.toBeInTheDocument()
    );
  });

  it('displays current priority value in the label', async () => {
    const user = userEvent.setup({ delay: null });
    render(<SteeringControls onCreateTopic={onCreateTopicMock as unknown as (data: TopicCreate) => Promise<TopicResponse>} />);
    await user.click(screen.getByRole('button', { name: /new topic/i }));
    // Default priority is 5
    expect(screen.getByText('Priority: 5')).toBeInTheDocument();
  });

  it('displays current target expertise percentage in the label', async () => {
    const user = userEvent.setup({ delay: null });
    render(<SteeringControls onCreateTopic={onCreateTopicMock as unknown as (data: TopicCreate) => Promise<TopicResponse>} />);
    await user.click(screen.getByRole('button', { name: /new topic/i }));
    // Default target_expertise is 0.8 → 80%
    expect(screen.getByText('Target Expertise: 80%')).toBeInTheDocument();
  });
});
