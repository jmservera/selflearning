import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { TopicSummary } from '../TopicSummary';
import type { TopicDetail } from '@/lib/types';

const mockTopicDetail: TopicDetail = {
  id: 'topic-1',
  name: 'Machine Learning',
  description: 'A comprehensive study of ML algorithms and applications',
  status: 'active',
  priority: 7,
  current_expertise: 45,
  target_expertise: 100,
  entity_count: 300,
  claim_count: 800,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-10T00:00:00Z',
  seed_urls: ['https://example.com/ml'],
  tags: ['ai', 'data-science'],
  coverage_areas: ['Supervised Learning', 'Neural Networks'],
  avg_confidence: 0.75,
  relationship_count: 120,
  source_count: 45,
  learning_cycles_completed: 5,
  last_learning_cycle: '2024-01-10T10:00:00Z',
  gap_areas: ['Reinforcement Learning'],
};

describe('TopicSummary', () => {
  it('renders the topic name', () => {
    render(<TopicSummary topic={mockTopicDetail} />);
    expect(screen.getByText('Machine Learning')).toBeInTheDocument();
  });

  it('renders the topic description', () => {
    render(<TopicSummary topic={mockTopicDetail} />);
    expect(screen.getByText('A comprehensive study of ML algorithms and applications')).toBeInTheDocument();
  });

  it('renders the status badge', () => {
    render(<TopicSummary topic={mockTopicDetail} />);
    expect(screen.getByText('active')).toBeInTheDocument();
  });

  it('renders expertise progress numbers', () => {
    render(<TopicSummary topic={mockTopicDetail} />);
    expect(screen.getByText('45 / 100')).toBeInTheDocument();
  });

  it('renders entity count', () => {
    render(<TopicSummary topic={mockTopicDetail} />);
    expect(screen.getByText('300')).toBeInTheDocument();
  });

  it('renders claim count', () => {
    render(<TopicSummary topic={mockTopicDetail} />);
    expect(screen.getByText('800')).toBeInTheDocument();
  });

  it('renders relationship count', () => {
    render(<TopicSummary topic={mockTopicDetail} />);
    expect(screen.getByText('120')).toBeInTheDocument();
  });

  it('renders source count', () => {
    render(<TopicSummary topic={mockTopicDetail} />);
    expect(screen.getByText('45')).toBeInTheDocument();
  });

  it('renders coverage areas as tags', () => {
    render(<TopicSummary topic={mockTopicDetail} />);
    expect(screen.getByText('Supervised Learning')).toBeInTheDocument();
    expect(screen.getByText('Neural Networks')).toBeInTheDocument();
  });

  it('renders learning cycles completed', () => {
    render(<TopicSummary topic={mockTopicDetail} />);
    expect(screen.getByText('5')).toBeInTheDocument();
  });

  it('renders "Never" when last_learning_cycle is null', () => {
    render(<TopicSummary topic={{ ...mockTopicDetail, last_learning_cycle: null }} />);
    expect(screen.getByText('Never')).toBeInTheDocument();
  });

  it('renders confidence bar with avg_confidence', () => {
    render(<TopicSummary topic={mockTopicDetail} />);
    expect(screen.getByText('75%')).toBeInTheDocument();
  });

  it('renders paused status badge with amber color class', () => {
    render(<TopicSummary topic={{ ...mockTopicDetail, status: 'paused' }} />);
    const badge = screen.getByText('paused');
    expect(badge.className).toContain('amber');
  });

  it('does not render coverage areas section when empty', () => {
    render(<TopicSummary topic={{ ...mockTopicDetail, coverage_areas: [] }} />);
    expect(screen.queryByText('Coverage Areas')).not.toBeInTheDocument();
  });
});
