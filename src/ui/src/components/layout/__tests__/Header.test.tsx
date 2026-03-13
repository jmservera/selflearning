import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { Header } from '../Header';

vi.mock('@/hooks/useWebSocket', () => ({
  useWebSocket: vi.fn(() => ({
    messages: [],
    isConnected: false,
    lastMessage: null,
    send: vi.fn(),
  })),
}));

describe('Header', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders system health status', () => {
    render(
      <MemoryRouter>
        <Header onMenuClick={vi.fn()} />
      </MemoryRouter>
    );
    expect(screen.getByText(/System:/)).toBeInTheDocument();
    expect(screen.getByText('healthy')).toBeInTheDocument();
  });

  it('shows Disconnected when WebSocket is not connected', () => {
    render(
      <MemoryRouter>
        <Header onMenuClick={vi.fn()} />
      </MemoryRouter>
    );
    expect(screen.getByText('Disconnected')).toBeInTheDocument();
  });

  it('shows Connected when WebSocket is connected', async () => {
    const { useWebSocket } = await import('@/hooks/useWebSocket');
    vi.mocked(useWebSocket).mockReturnValue({
      messages: [],
      isConnected: true,
      lastMessage: null,
      send: vi.fn(),
    });

    render(
      <MemoryRouter>
        <Header onMenuClick={vi.fn()} />
      </MemoryRouter>
    );
    expect(screen.getByText('Connected')).toBeInTheDocument();
  });

  it('calls onMenuClick when hamburger button is clicked', async () => {
    const onMenuClick = vi.fn();
    const user = userEvent.setup({ delay: null });
    render(
      <MemoryRouter>
        <Header onMenuClick={onMenuClick} />
      </MemoryRouter>
    );
    await user.click(screen.getByLabelText('Toggle menu'));
    expect(onMenuClick).toHaveBeenCalledTimes(1);
  });
});
