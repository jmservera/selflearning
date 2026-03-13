import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ProgressChart } from '../ProgressChart';
import type { LearningProgress, TopicResponse } from '@/lib/types';

const mockTopic: TopicResponse = {
  id: 'topic-1',
  name: 'Machine Learning',
  status: 'active',
  priority: 5,
  current_expertise: 60,
  target_expertise: 100,
  entity_count: 300,
  claim_count: 700,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-02T00:00:00Z',
};

const mockProgress: LearningProgress = {
  topics: [mockTopic],
  overall_expertise: 0.45,
  total_entities: 5000,
  total_claims: 12000,
  total_sources: 300,
  learning_rate: 12.5,
};

const defaultProps = {
  onStartLearning: vi.fn().mockResolvedValue(undefined),
  onPause: vi.fn().mockResolvedValue(undefined),
  onResume: vi.fn().mockResolvedValue(undefined),
  onUpdatePriority: vi.fn().mockResolvedValue(undefined),
};

describe('ProgressChart', () => {
  it('shows loading skeleton when progress is null', () => {
    const { container } = render(<ProgressChart {...defaultProps} progress={null} />);
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
    expect(screen.queryByText('Learning Progress')).not.toBeInTheDocument();
  });

  it('renders the Learning Progress heading', () => {
    render(<ProgressChart {...defaultProps} progress={mockProgress} />);
    expect(screen.getByText('Learning Progress')).toBeInTheDocument();
  });

  it('renders overall expertise percentage', () => {
    render(<ProgressChart {...defaultProps} progress={mockProgress} />);
    expect(screen.getByText('45.0%')).toBeInTheDocument();
  });

  it('renders total entities with locale formatting', () => {
    render(<ProgressChart {...defaultProps} progress={mockProgress} />);
    expect(screen.getByText('5,000')).toBeInTheDocument();
  });

  it('renders total claims with locale formatting', () => {
    render(<ProgressChart {...defaultProps} progress={mockProgress} />);
    expect(screen.getByText('12,000')).toBeInTheDocument();
  });

  it('renders learning rate', () => {
    render(<ProgressChart {...defaultProps} progress={mockProgress} />);
    expect(screen.getByText('12.5 entities/hr')).toBeInTheDocument();
  });

  it('renders topic cards for each topic', () => {
    render(<ProgressChart {...defaultProps} progress={mockProgress} />);
    expect(screen.getByText('Machine Learning')).toBeInTheDocument();
  });

  it('shows empty state when no topics exist', () => {
    const emptyProgress: LearningProgress = { ...mockProgress, topics: [] };
    render(<ProgressChart {...defaultProps} progress={emptyProgress} />);
    expect(screen.getByText('No topics yet. Create a topic to start learning.')).toBeInTheDocument();
  });
});
