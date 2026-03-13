import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { Sidebar } from '../Sidebar';

describe('Sidebar', () => {
  it('renders navigation links', () => {
    render(
      <MemoryRouter>
        <Sidebar isOpen={true} onToggle={vi.fn()} />
      </MemoryRouter>
    );
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Knowledge Explorer')).toBeInTheDocument();
    expect(screen.getByText('Chat')).toBeInTheDocument();
  });

  it('hides nav labels when collapsed', () => {
    render(
      <MemoryRouter>
        <Sidebar isOpen={false} onToggle={vi.fn()} />
      </MemoryRouter>
    );
    expect(screen.queryByText('Dashboard')).not.toBeInTheDocument();
    expect(screen.queryByText('Knowledge Explorer')).not.toBeInTheDocument();
  });

  it('shows Self-Learning title when open', () => {
    render(
      <MemoryRouter>
        <Sidebar isOpen={true} onToggle={vi.fn()} />
      </MemoryRouter>
    );
    expect(screen.getByText('Self-Learning')).toBeInTheDocument();
  });

  it('hides title when collapsed', () => {
    render(
      <MemoryRouter>
        <Sidebar isOpen={false} onToggle={vi.fn()} />
      </MemoryRouter>
    );
    expect(screen.queryByText('Self-Learning')).not.toBeInTheDocument();
  });

  it('calls onToggle when toggle button is clicked', async () => {
    const onToggle = vi.fn();
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <Sidebar isOpen={true} onToggle={onToggle} />
      </MemoryRouter>
    );
    await user.click(screen.getByLabelText('Collapse sidebar'));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it('shows expand label when sidebar is collapsed', () => {
    render(
      <MemoryRouter>
        <Sidebar isOpen={false} onToggle={vi.fn()} />
      </MemoryRouter>
    );
    expect(screen.getByLabelText('Expand sidebar')).toBeInTheDocument();
  });

  it('shows version info when expanded', () => {
    render(
      <MemoryRouter>
        <Sidebar isOpen={true} onToggle={vi.fn()} />
      </MemoryRouter>
    );
    expect(screen.getByText('v0.0.1')).toBeInTheDocument();
    expect(screen.getByText('Control UI')).toBeInTheDocument();
  });
});
