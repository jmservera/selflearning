import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { Layout } from '../Layout';

vi.mock('@/hooks/useWebSocket', () => ({
  useWebSocket: vi.fn(() => ({
    messages: [],
    isConnected: false,
    lastMessage: null,
    send: vi.fn(),
  })),
}));

describe('Layout', () => {
  it('renders the sidebar and header', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<div>Page content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByText('Self-Learning')).toBeInTheDocument();
    expect(screen.getByText(/System:/)).toBeInTheDocument();
  });

  it('renders the outlet (child page content)', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<div>My Page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByText('My Page')).toBeInTheDocument();
  });
});
