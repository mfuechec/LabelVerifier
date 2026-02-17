import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import HistoryPage from './HistoryPage';
import { createMockHistoryItem } from '../test/utils';

let mockData: { items: ReturnType<typeof createMockHistoryItem>[]; total: number; page: number; per_page: number } | undefined;
let mockIsLoading = false;

vi.mock('../api/verifications', () => ({
  useVerifications: () => ({
    data: mockData,
    isLoading: mockIsLoading,
  }),
}));

// Mock useNavigate for HistoryTable
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => vi.fn() };
});

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <HistoryPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('HistoryPage', () => {
  beforeEach(() => {
    mockData = {
      items: [
        createMockHistoryItem({ session_id: 's1', brand_name: 'Brand A' }),
        createMockHistoryItem({ session_id: 's2', brand_name: 'Brand B' }),
      ],
      total: 2,
      page: 1,
      per_page: 20,
    };
    mockIsLoading = false;
  });

  it('renders heading', () => {
    renderPage();
    expect(screen.getByText('Verification History')).toBeInTheDocument();
  });

  it('renders filters', () => {
    renderPage();
    expect(screen.getByText('All Statuses')).toBeInTheDocument();
    expect(screen.getByText('All Types')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Search by brand...')).toBeInTheDocument();
  });

  it('renders history items', () => {
    renderPage();
    expect(screen.getByText('Brand A')).toBeInTheDocument();
    expect(screen.getByText('Brand B')).toBeInTheDocument();
  });

  it('shows loading spinner', () => {
    mockIsLoading = true;
    mockData = undefined;
    renderPage();
    expect(screen.getByText('Loading history...')).toBeInTheDocument();
  });

  it('shows empty state when no items', () => {
    mockData = { items: [], total: 0, page: 1, per_page: 20 };
    renderPage();
    expect(screen.getByText('No verification records found.')).toBeInTheDocument();
  });

  it('shows pagination when total > per_page', () => {
    mockData = {
      items: [createMockHistoryItem()],
      total: 40,
      page: 1,
      per_page: 20,
    };
    renderPage();
    expect(screen.getByText('Previous')).toBeInTheDocument();
    expect(screen.getByText('Next')).toBeInTheDocument();
    expect(screen.getByText('Page 1 of 2')).toBeInTheDocument();
  });

  it('does not show pagination when all items fit on one page', () => {
    renderPage(); // total=2, per_page=20
    expect(screen.queryByText('Previous')).not.toBeInTheDocument();
  });

  it('disables Previous button on first page', () => {
    mockData = { items: [createMockHistoryItem()], total: 40, page: 1, per_page: 20 };
    renderPage();
    expect(screen.getByText('Previous')).toBeDisabled();
  });
});
