import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { GapAnalysis } from '../GapAnalysis';
import type { TopicDetail } from '@/lib/types';

const baseTopic: TopicDetail = {
  id: 'topic-1',
  name: 'Machine Learning',
  description: 'ML study',
  status: 'active',
  priority: 5,
  current_expertise: 50,
  target_expertise: 100,
  entity_count: 200,
  claim_count: 500,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-10T00:00:00Z',
  seed_urls: [],
  tags: [],
  coverage_areas: ['Supervised Learning', 'Neural Networks'],
  avg_confidence: 0.7,
  relationship_count: 50,
  source_count: 20,
  learning_cycles_completed: 3,
  last_learning_cycle: null,
  gap_areas: ['Reinforcement Learning', 'Transfer Learning', 'Meta-Learning'],
};

describe('GapAnalysis', () => {
  it('renders the Knowledge Gaps heading', () => {
    render(<GapAnalysis topic={baseTopic} />);
    expect(screen.getByText('Knowledge Gaps')).toBeInTheDocument();
  });

  it('renders completeness percentage', () => {
    render(<GapAnalysis topic={baseTopic} />);
    // 2 coverage / (2 + 3) = 40% complete
    expect(screen.getByText('40% Complete')).toBeInTheDocument();
  });

  it('shows covered and gap counts', () => {
    render(<GapAnalysis topic={baseTopic} />);
    expect(screen.getByText('2 covered')).toBeInTheDocument();
    expect(screen.getByText('3 gaps')).toBeInTheDocument();
  });

  it('renders Areas to Learn section with gap areas', () => {
    render(<GapAnalysis topic={baseTopic} />);
    expect(screen.getByText('Areas to Learn')).toBeInTheDocument();
    // Gap areas appear in both "Areas to Learn" and "Next Steps" sections
    expect(screen.getAllByText('Reinforcement Learning').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Transfer Learning').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Meta-Learning').length).toBeGreaterThan(0);
  });

  it('renders Next Steps section with first 3 gaps', () => {
    render(<GapAnalysis topic={baseTopic} />);
    expect(screen.getByText('Next Steps')).toBeInTheDocument();
    // All 3 gaps fit in the first 3
    expect(screen.getAllByText('Reinforcement Learning').length).toBeGreaterThan(0);
  });

  it('shows Well-Covered Areas when coverage_areas present', () => {
    render(<GapAnalysis topic={baseTopic} />);
    expect(screen.getByText('Well-Covered Areas')).toBeInTheDocument();
    expect(screen.getByText('Supervised Learning')).toBeInTheDocument();
    expect(screen.getByText('Neural Networks')).toBeInTheDocument();
  });

  it('shows "No significant gaps identified" when gap_areas is empty', () => {
    render(<GapAnalysis topic={{ ...baseTopic, gap_areas: [] }} />);
    expect(screen.getByText('No significant gaps identified')).toBeInTheDocument();
  });

  it('renders 0% Complete when coverage_areas is empty', () => {
    render(<GapAnalysis topic={{ ...baseTopic, coverage_areas: [] }} />);
    expect(screen.getByText('0% Complete')).toBeInTheDocument();
  });

  it('marks first gap as critical when 3 or fewer gaps', () => {
    render(<GapAnalysis topic={baseTopic} />);
    expect(screen.getByText('High priority - critical knowledge gap')).toBeInTheDocument();
  });

  it('shows "...and N more areas" when more than 3 gaps', () => {
    const manyGaps = {
      ...baseTopic,
      gap_areas: ['Gap1', 'Gap2', 'Gap3', 'Gap4', 'Gap5'],
    };
    render(<GapAnalysis topic={manyGaps} />);
    expect(screen.getByText('...and 2 more areas')).toBeInTheDocument();
  });

  it('shows "+N more" for coverage areas when more than 5', () => {
    const manyCoverage = {
      ...baseTopic,
      coverage_areas: ['A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7'],
    };
    render(<GapAnalysis topic={manyCoverage} />);
    expect(screen.getByText('+2 more')).toBeInTheDocument();
  });
});
