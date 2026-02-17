import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import HistoryTable from './HistoryTable';
import { createMockHistoryItem } from '../../test/utils';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

describe('HistoryTable', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
  });

  it('renders rows for each history item', () => {
    const items = [
      createMockHistoryItem({ session_id: 's1', brand_name: 'Brand A' }),
      createMockHistoryItem({ session_id: 's2', brand_name: 'Brand B' }),
    ];
    render(<HistoryTable items={items} />, { wrapper: MemoryRouter });
    expect(screen.getByText('Brand A')).toBeInTheDocument();
    expect(screen.getByText('Brand B')).toBeInTheDocument();
  });

  it('shows empty state when no items', () => {
    render(<HistoryTable items={[]} />, { wrapper: MemoryRouter });
    expect(screen.getByText('No verification records found.')).toBeInTheDocument();
  });

  it('navigates on row click', () => {
    const items = [createMockHistoryItem({ session_id: 'abc-123' })];
    render(<HistoryTable items={items} />, { wrapper: MemoryRouter });
    const row = screen.getByText('Test Brand').closest('tr')!;
    fireEvent.click(row);
    expect(mockNavigate).toHaveBeenCalledWith('/verify/abc-123');
  });

  it('renders table headers', () => {
    render(<HistoryTable items={[createMockHistoryItem()]} />, { wrapper: MemoryRouter });
    expect(screen.getByText('Brand')).toBeInTheDocument();
    expect(screen.getByText('Type')).toBeInTheDocument();
    expect(screen.getByText('Status')).toBeInTheDocument();
    expect(screen.getByText('Confidence')).toBeInTheDocument();
    expect(screen.getByText('Decision')).toBeInTheDocument();
    expect(screen.getByText('Date')).toBeInTheDocument();
  });

  it('shows dash for null brand name', () => {
    const items = [createMockHistoryItem({ brand_name: null })];
    render(<HistoryTable items={items} />, { wrapper: MemoryRouter });
    const brandCell = screen.getAllByText('-');
    expect(brandCell.length).toBeGreaterThanOrEqual(1);
  });

  it('formats processing time in seconds', () => {
    const items = [createMockHistoryItem({ processing_time_ms: 4500 })];
    render(<HistoryTable items={items} />, { wrapper: MemoryRouter });
    expect(screen.getByText('4.5s')).toBeInTheDocument();
  });

  it('formats token count with K suffix', () => {
    const items = [createMockHistoryItem({ total_tokens: 12500 })];
    render(<HistoryTable items={items} />, { wrapper: MemoryRouter });
    expect(screen.getByText('12.5K')).toBeInTheDocument();
  });

  it('formats cost with dollar sign', () => {
    const items = [createMockHistoryItem({ estimated_cost_usd: 0.0125 })];
    render(<HistoryTable items={items} />, { wrapper: MemoryRouter });
    expect(screen.getByText('$0.0125')).toBeInTheDocument();
  });
});
