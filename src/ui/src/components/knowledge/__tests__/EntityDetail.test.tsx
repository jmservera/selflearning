import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest';
import { EntityDetail } from '../EntityDetail';
import type { Entity } from '@/lib/types';

beforeAll(() => {
  window.HTMLElement.prototype.scrollIntoView = () => {};
});

vi.mock('@/lib/api', () => ({
  api: {
    knowledge: {
      getEntity: vi.fn(),
    },
  },
}));

import { api } from '@/lib/api';

const mockEntity: Entity = {
  id: 'e1',
  name: 'Neural Network',
  entity_type: 'concept',
  description: 'A computational model inspired by the brain.',
  topic: 'machine-learning',
  confidence: 0.85,
  source_urls: ['https://example.com/nn', 'https://another.com/nn'],
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-10T00:00:00Z',
  relationships: [
    {
      id: 'rel-1',
      target_entity_id: 'e2',
      target_name: 'Deep Learning',
      relationship_type: 'is_part_of',
      confidence: 0.9,
    },
  ],
  claims: [
    {
      id: 'claim-1',
      statement: 'Neural networks learn from data.',
      confidence: 0.8,
      source_url: 'https://example.com/claim',
    },
  ],
};

describe('EntityDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading spinner initially', () => {
    vi.mocked(api.knowledge.getEntity).mockReturnValue(new Promise(() => {}));
    const { container } = render(<EntityDetail entityId="e1" onClose={vi.fn()} />);
    expect(container.querySelector('.animate-spin')).toBeInTheDocument();
  });

  it('renders entity name after loading', async () => {
    vi.mocked(api.knowledge.getEntity).mockResolvedValue(mockEntity);
    render(<EntityDetail entityId="e1" onClose={vi.fn()} />);
    await waitFor(() => screen.getByText('Neural Network'));
    expect(screen.getByText('Neural Network')).toBeInTheDocument();
  });

  it('renders entity type badge', async () => {
    vi.mocked(api.knowledge.getEntity).mockResolvedValue(mockEntity);
    render(<EntityDetail entityId="e1" onClose={vi.fn()} />);
    await waitFor(() => screen.getByText('concept'));
    expect(screen.getByText('concept')).toBeInTheDocument();
  });

  it('renders entity description', async () => {
    vi.mocked(api.knowledge.getEntity).mockResolvedValue(mockEntity);
    render(<EntityDetail entityId="e1" onClose={vi.fn()} />);
    await waitFor(() => screen.getByText('A computational model inspired by the brain.'));
    expect(screen.getByText('A computational model inspired by the brain.')).toBeInTheDocument();
  });

  it('renders source URLs', async () => {
    vi.mocked(api.knowledge.getEntity).mockResolvedValue(mockEntity);
    render(<EntityDetail entityId="e1" onClose={vi.fn()} />);
    await waitFor(() => screen.getByText('Sources (2)'));
    expect(screen.getByText('example.com')).toBeInTheDocument();
  });

  it('renders relationships', async () => {
    vi.mocked(api.knowledge.getEntity).mockResolvedValue(mockEntity);
    render(<EntityDetail entityId="e1" onClose={vi.fn()} />);
    await waitFor(() => screen.getByText('Deep Learning'));
    expect(screen.getByText('is_part_of')).toBeInTheDocument();
  });

  it('renders claims', async () => {
    vi.mocked(api.knowledge.getEntity).mockResolvedValue(mockEntity);
    render(<EntityDetail entityId="e1" onClose={vi.fn()} />);
    await waitFor(() => screen.getByText('Neural networks learn from data.'));
    expect(screen.getByText('Neural networks learn from data.')).toBeInTheDocument();
  });

  it('shows error message when loading fails', async () => {
    vi.mocked(api.knowledge.getEntity).mockRejectedValue(new Error('Not found'));
    render(<EntityDetail entityId="e1" onClose={vi.fn()} />);
    await waitFor(() => screen.getByText('Failed to load entity details'));
    expect(screen.getByText('Failed to load entity details')).toBeInTheDocument();
  });

  it('calls onClose when close button is clicked', async () => {
    vi.mocked(api.knowledge.getEntity).mockResolvedValue(mockEntity);
    const onClose = vi.fn();
    const user = userEvent.setup({ delay: null });
    render(<EntityDetail entityId="e1" onClose={onClose} />);
    await user.click(screen.getByRole('button'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('passes topic to getEntity when provided', async () => {
    vi.mocked(api.knowledge.getEntity).mockResolvedValue(mockEntity);
    render(<EntityDetail entityId="e1" topic="ml" onClose={vi.fn()} />);
    await waitFor(() => expect(api.knowledge.getEntity).toHaveBeenCalledWith('e1', 'ml'));
  });
});
