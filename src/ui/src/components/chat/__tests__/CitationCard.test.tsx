import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect } from 'vitest';
import { CitationCard } from '../CitationCard';
import type { Citation } from '@/lib/types';

const baseCitation: Citation = {
  entity_id: 'e1',
  name: 'Neural Networks Overview',
  source_url: 'https://example.com/neural-networks',
  confidence: 0.85,
  snippet: 'A neural network is a series of algorithms that attempt to recognize underlying relationships in a set of data.',
};

const longSnippetCitation: Citation = {
  ...baseCitation,
  snippet:
    'A neural network is a series of algorithms that attempt to recognize underlying relationships in a set of data through a process that mimics the way the human brain operates in some ways. Neural networks can adapt to changing input so the network generates the best possible result.',
};

describe('CitationCard', () => {
  it('renders the citation name', () => {
    render(<CitationCard citation={baseCitation} />);
    expect(screen.getByText('Neural Networks Overview')).toBeInTheDocument();
  });

  it('renders the source URL hostname as a link', () => {
    render(<CitationCard citation={baseCitation} />);
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', 'https://example.com/neural-networks');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveTextContent('example.com');
  });

  it('renders the confidence bar', () => {
    render(<CitationCard citation={baseCitation} />);
    expect(screen.getByText('85%')).toBeInTheDocument();
  });

  it('renders short snippets without expand button', () => {
    render(<CitationCard citation={baseCitation} />);
    expect(screen.queryByRole('button', { name: /show more/i })).not.toBeInTheDocument();
    expect(screen.getByText(baseCitation.snippet)).toBeInTheDocument();
  });

  it('truncates long snippets and shows a "Show more" button', () => {
    render(<CitationCard citation={longSnippetCitation} />);
    const showMoreBtn = screen.getByRole('button', { name: /show more/i });
    expect(showMoreBtn).toBeInTheDocument();
    // Full snippet should not be visible yet
    expect(screen.queryByText(longSnippetCitation.snippet)).not.toBeInTheDocument();
  });

  it('expands the snippet when "Show more" is clicked', async () => {
    const user = userEvent.setup({ delay: null });
    render(<CitationCard citation={longSnippetCitation} />);
    await user.click(screen.getByRole('button', { name: /show more/i }));
    expect(screen.getByText(longSnippetCitation.snippet)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /show less/i })).toBeInTheDocument();
  });

  it('collapses the snippet when "Show less" is clicked', async () => {
    const user = userEvent.setup({ delay: null });
    render(<CitationCard citation={longSnippetCitation} />);
    await user.click(screen.getByRole('button', { name: /show more/i }));
    await user.click(screen.getByRole('button', { name: /show less/i }));
    expect(screen.queryByText(longSnippetCitation.snippet)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /show more/i })).toBeInTheDocument();
  });
});
