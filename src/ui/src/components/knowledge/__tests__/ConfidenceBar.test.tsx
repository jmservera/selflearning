import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ConfidenceBar } from '../ConfidenceBar';

describe('ConfidenceBar', () => {
  describe('bar variant (default)', () => {
    it('renders the percentage label by default', () => {
      render(<ConfidenceBar value={0.75} />);
      expect(screen.getByText('75%')).toBeInTheDocument();
    });

    it('hides the label when showLabel is false', () => {
      render(<ConfidenceBar value={0.75} showLabel={false} />);
      expect(screen.queryByText('75%')).not.toBeInTheDocument();
    });

    it('applies low-confidence (rose) color for value < 0.3', () => {
      const { container } = render(<ConfidenceBar value={0.2} />);
      const bar = container.querySelector('.bg-gradient-to-r');
      expect(bar?.className).toContain('from-rose-500');
    });

    it('applies medium-confidence (amber) color for 0.3 ≤ value < 0.7', () => {
      const { container } = render(<ConfidenceBar value={0.5} />);
      const bar = container.querySelector('.bg-gradient-to-r');
      expect(bar?.className).toContain('from-amber-500');
    });

    it('applies high-confidence (emerald) color for value ≥ 0.7', () => {
      const { container } = render(<ConfidenceBar value={0.8} />);
      const bar = container.querySelector('.bg-gradient-to-r');
      expect(bar?.className).toContain('from-emerald-500');
    });

    it('renders correct width style for the bar fill', () => {
      const { container } = render(<ConfidenceBar value={0.6} />);
      const fill = container.querySelector('.bg-gradient-to-r');
      expect(fill).toHaveStyle({ width: '60%' });
    });

    it('rounds the percentage value', () => {
      render(<ConfidenceBar value={0.755} />);
      expect(screen.getByText('76%')).toBeInTheDocument();
    });
  });

  describe('ring variant', () => {
    it('renders an SVG for the ring variant', () => {
      const { container } = render(<ConfidenceBar value={0.5} variant="ring" />);
      expect(container.querySelector('svg')).toBeInTheDocument();
    });

    it('shows the percentage inside the ring when showLabel is true', () => {
      render(<ConfidenceBar value={0.4} variant="ring" showLabel={true} />);
      expect(screen.getByText('40%')).toBeInTheDocument();
    });

    it('hides the percentage inside the ring when showLabel is false', () => {
      render(<ConfidenceBar value={0.4} variant="ring" showLabel={false} />);
      expect(screen.queryByText('40%')).not.toBeInTheDocument();
    });
  });
});
