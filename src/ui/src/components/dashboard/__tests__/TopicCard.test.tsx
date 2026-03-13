import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { TopicCard } from '../TopicCard';
import type { TopicResponse } from '@/lib/types';

const baseTopic: TopicResponse = {
  id: 'topic-1',
  name: 'Machine Learning',
  description: 'Learn about ML fundamentals',
  status: 'pending',
  priority: 5,
  current_expertise: 30,
  target_expertise: 100,
  entity_count: 150,
  claim_count: 300,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-02T00:00:00Z',
};

const defaultProps = {
  topic: baseTopic,
  onStartLearning: vi.fn().mockResolvedValue(undefined),
  onPause: vi.fn().mockResolvedValue(undefined),
  onResume: vi.fn().mockResolvedValue(undefined),
  onUpdatePriority: vi.fn().mockResolvedValue(undefined),
};

describe('TopicCard', () => {
  it('renders the topic name', () => {
    render(<TopicCard {...defaultProps} />);
    expect(screen.getByText('Machine Learning')).toBeInTheDocument();
  });

  it('renders the topic description', () => {
    render(<TopicCard {...defaultProps} />);
    expect(screen.getByText('Learn about ML fundamentals')).toBeInTheDocument();
  });

  it('shows the pending status badge', () => {
    render(<TopicCard {...defaultProps} />);
    expect(screen.getByText('Pending')).toBeInTheDocument();
  });

  it('shows the active status badge for active topic', () => {
    render(<TopicCard {...defaultProps} topic={{ ...baseTopic, status: 'active' }} />);
    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('shows the paused status badge for paused topic', () => {
    render(<TopicCard {...defaultProps} topic={{ ...baseTopic, status: 'paused' }} />);
    expect(screen.getByText('Paused')).toBeInTheDocument();
  });

  it('renders entity count and claim count', () => {
    render(<TopicCard {...defaultProps} />);
    expect(screen.getByText('150')).toBeInTheDocument();
    expect(screen.getByText('300')).toBeInTheDocument();
  });

  it('displays progress percentage', () => {
    render(<TopicCard {...defaultProps} />);
    // 30 / 100 * 100 = 30%
    expect(screen.getByText('30%')).toBeInTheDocument();
  });

  it('shows Start Learning button for pending topics', () => {
    render(<TopicCard {...defaultProps} />);
    expect(screen.getByTitle('Start Learning')).toBeInTheDocument();
  });

  it('calls onStartLearning when Start Learning is clicked', async () => {
    const onStartLearning = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup({ delay: null });
    render(<TopicCard {...defaultProps} onStartLearning={onStartLearning} />);
    await user.click(screen.getByTitle('Start Learning'));
    expect(onStartLearning).toHaveBeenCalledWith('topic-1');
  });

  it('shows Pause button for active topics', () => {
    render(<TopicCard {...defaultProps} topic={{ ...baseTopic, status: 'active' }} />);
    expect(screen.getByTitle('Pause')).toBeInTheDocument();
  });

  it('calls onPause when Pause is clicked', async () => {
    const onPause = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup({ delay: null });
    render(
      <TopicCard {...defaultProps} topic={{ ...baseTopic, status: 'active' }} onPause={onPause} />
    );
    await user.click(screen.getByTitle('Pause'));
    expect(onPause).toHaveBeenCalledWith('topic-1');
  });

  it('shows Resume button for paused topics', () => {
    render(<TopicCard {...defaultProps} topic={{ ...baseTopic, status: 'paused' }} />);
    expect(screen.getByTitle('Resume')).toBeInTheDocument();
  });

  it('calls onResume when Resume is clicked', async () => {
    const onResume = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup({ delay: null });
    render(
      <TopicCard {...defaultProps} topic={{ ...baseTopic, status: 'paused' }} onResume={onResume} />
    );
    await user.click(screen.getByTitle('Resume'));
    expect(onResume).toHaveBeenCalledWith('topic-1');
  });

  it('calls onUpdatePriority with incremented value on up arrow click', async () => {
    const onUpdatePriority = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup({ delay: null });
    render(<TopicCard {...defaultProps} onUpdatePriority={onUpdatePriority} />);
    await user.click(screen.getByTitle('Increase Priority'));
    expect(onUpdatePriority).toHaveBeenCalledWith('topic-1', 6);
  });

  it('calls onUpdatePriority with decremented value on down arrow click', async () => {
    const onUpdatePriority = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup({ delay: null });
    render(<TopicCard {...defaultProps} onUpdatePriority={onUpdatePriority} />);
    await user.click(screen.getByTitle('Decrease Priority'));
    expect(onUpdatePriority).toHaveBeenCalledWith('topic-1', 4);
  });

  it('disables increase priority button at max priority (10)', () => {
    render(<TopicCard {...defaultProps} topic={{ ...baseTopic, priority: 10 }} />);
    expect(screen.getByTitle('Increase Priority')).toBeDisabled();
  });

  it('disables decrease priority button at min priority (1)', () => {
    render(<TopicCard {...defaultProps} topic={{ ...baseTopic, priority: 1 }} />);
    expect(screen.getByTitle('Decrease Priority')).toBeDisabled();
  });

  it('renders 10 priority indicator dots', () => {
    const { container } = render(<TopicCard {...defaultProps} />);
    // Each dot is rendered as a Circle icon (svg)
    const svgs = container.querySelectorAll('.mt-3 svg');
    expect(svgs.length).toBe(10);
  });
});
