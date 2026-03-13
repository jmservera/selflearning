import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeAll } from 'vitest';
import { GraphView } from '../GraphView';

beforeAll(() => {
  // jsdom doesn't fully implement getBoundingClientRect
  Element.prototype.getBoundingClientRect = () => ({
    width: 800,
    height: 600,
    top: 0,
    left: 0,
    bottom: 600,
    right: 800,
    x: 0,
    y: 0,
    toJSON: () => {},
  });
});

const mockEntities = [
  {
    id: 'e1',
    name: 'Neural Network',
    entity_type: 'concept',
    confidence: 0.9,
    description: 'A neural network.',
    topic: 'ml',
    source_urls: [],
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 'e2',
    name: 'Deep Learning',
    entity_type: 'concept',
    confidence: 0.5,
    description: 'Deep learning.',
    topic: 'ml',
    source_urls: [],
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
];

const mockRelationships = [
  {
    id: 'r1',
    source_entity_id: 'e1',
    target_entity_id: 'e2',
    relationship_type: 'related_to',
    confidence: 0.8,
    topic: 'ml',
  },
];

describe('GraphView', () => {
  it('shows empty state when no entities are provided', () => {
    render(
      <GraphView
        entities={[]}
        relationships={[]}
        onNodeSelect={vi.fn()}
      />
    );
    expect(screen.getByText('No entities to display')).toBeInTheDocument();
  });

  it('renders zoom control buttons', () => {
    render(
      <GraphView
        entities={mockEntities}
        relationships={mockRelationships}
        onNodeSelect={vi.fn()}
      />
    );
    expect(screen.getByTitle('Zoom in')).toBeInTheDocument();
    expect(screen.getByTitle('Zoom out')).toBeInTheDocument();
    expect(screen.getByTitle('Reset view')).toBeInTheDocument();
  });

  it('renders the legend', () => {
    render(
      <GraphView
        entities={mockEntities}
        relationships={mockRelationships}
        onNodeSelect={vi.fn()}
      />
    );
    expect(screen.getByText('Confidence')).toBeInTheDocument();
    expect(screen.getByText(/High/)).toBeInTheDocument();
    expect(screen.getByText(/Medium/)).toBeInTheDocument();
    expect(screen.getByText(/Low/)).toBeInTheDocument();
  });

  it('renders an SVG canvas for the graph', () => {
    const { container } = render(
      <GraphView
        entities={mockEntities}
        relationships={mockRelationships}
        onNodeSelect={vi.fn()}
      />
    );
    expect(container.querySelector('svg')).toBeInTheDocument();
  });

  it('calls zoom in when zoom in button is clicked', async () => {
    const user = userEvent.setup({ delay: null });
    render(
      <GraphView
        entities={mockEntities}
        relationships={mockRelationships}
        onNodeSelect={vi.fn()}
      />
    );
    // Clicking zoom in should not throw
    await user.click(screen.getByTitle('Zoom in'));
    await user.click(screen.getByTitle('Zoom out'));
    await user.click(screen.getByTitle('Reset view'));
  });
});
