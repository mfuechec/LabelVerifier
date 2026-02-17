import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import HistoryFilters from './HistoryFilters';

describe('HistoryFilters', () => {
  const defaultProps = {
    status: '',
    beverageType: '',
    search: '',
    onStatusChange: vi.fn(),
    onBeverageTypeChange: vi.fn(),
    onSearchChange: vi.fn(),
  };

  it('renders status dropdown with all options', () => {
    render(<HistoryFilters {...defaultProps} />);
    expect(screen.getByText('All Statuses')).toBeInTheDocument();
    expect(screen.getByText('Pass')).toBeInTheDocument();
    expect(screen.getByText('Needs Review')).toBeInTheDocument();
    expect(screen.getByText('Fail')).toBeInTheDocument();
  });

  it('renders beverage type dropdown', () => {
    render(<HistoryFilters {...defaultProps} />);
    expect(screen.getByText('All Types')).toBeInTheDocument();
    expect(screen.getByText('Distilled Spirits')).toBeInTheDocument();
    expect(screen.getByText('Wine')).toBeInTheDocument();
    expect(screen.getByText('Beer')).toBeInTheDocument();
  });

  it('renders search input', () => {
    render(<HistoryFilters {...defaultProps} />);
    expect(screen.getByPlaceholderText('Search by brand...')).toBeInTheDocument();
  });

  it('calls onStatusChange when status is selected', () => {
    const onStatusChange = vi.fn();
    render(<HistoryFilters {...defaultProps} onStatusChange={onStatusChange} />);
    const selects = screen.getAllByRole('combobox');
    fireEvent.change(selects[0], { target: { value: 'pass' } });
    expect(onStatusChange).toHaveBeenCalledWith('pass');
  });

  it('calls onBeverageTypeChange when type is selected', () => {
    const onBeverageTypeChange = vi.fn();
    render(<HistoryFilters {...defaultProps} onBeverageTypeChange={onBeverageTypeChange} />);
    const selects = screen.getAllByRole('combobox');
    fireEvent.change(selects[1], { target: { value: 'wine' } });
    expect(onBeverageTypeChange).toHaveBeenCalledWith('wine');
  });

  it('calls onSearchChange when typing in search input', () => {
    const onSearchChange = vi.fn();
    render(<HistoryFilters {...defaultProps} onSearchChange={onSearchChange} />);
    fireEvent.change(screen.getByPlaceholderText('Search by brand...'), {
      target: { value: 'Smirnoff' },
    });
    expect(onSearchChange).toHaveBeenCalledWith('Smirnoff');
  });
});
