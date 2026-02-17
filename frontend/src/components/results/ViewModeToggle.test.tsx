import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import ViewModeToggle from './ViewModeToggle';

describe('ViewModeToggle', () => {
  it('renders both mode buttons', () => {
    render(<ViewModeToggle mode="comparison" onModeChange={vi.fn()} />);
    expect(screen.getByText('Comparison Table')).toBeInTheDocument();
    expect(screen.getByText('Extracted Text')).toBeInTheDocument();
  });

  it('calls onModeChange with "comparison" when clicking Comparison Table', () => {
    const onModeChange = vi.fn();
    render(<ViewModeToggle mode="extracted" onModeChange={onModeChange} />);
    fireEvent.click(screen.getByText('Comparison Table'));
    expect(onModeChange).toHaveBeenCalledWith('comparison');
  });

  it('calls onModeChange with "extracted" when clicking Extracted Text', () => {
    const onModeChange = vi.fn();
    render(<ViewModeToggle mode="comparison" onModeChange={onModeChange} />);
    fireEvent.click(screen.getByText('Extracted Text'));
    expect(onModeChange).toHaveBeenCalledWith('extracted');
  });

  it('highlights active comparison mode with bold font weight', () => {
    render(<ViewModeToggle mode="comparison" onModeChange={vi.fn()} />);
    const btn = screen.getByText('Comparison Table');
    expect(btn.style.fontWeight).toBe('600');
  });

  it('highlights active extracted mode with bold font weight', () => {
    render(<ViewModeToggle mode="extracted" onModeChange={vi.fn()} />);
    const btn = screen.getByText('Extracted Text');
    expect(btn.style.fontWeight).toBe('600');
  });
});
