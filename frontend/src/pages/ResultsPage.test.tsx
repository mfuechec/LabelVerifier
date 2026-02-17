import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ResultsPage from './ResultsPage';
import { createMockVerification, createMockField } from '../test/utils';

const mockOverrideMutate = vi.fn();
const mockDecisionMutate = vi.fn();
const mockFeedbackMutate = vi.fn();
const mockReviewMutate = vi.fn();

let mockVerificationData: ReturnType<typeof createMockVerification> | undefined;
let mockIsLoading = false;
let mockError: Error | null = null;

vi.mock('../api/verifications', () => ({
  useVerification: () => ({
    data: mockVerificationData,
    isLoading: mockIsLoading,
    error: mockError,
  }),
  useOverrideField: () => ({
    mutate: mockOverrideMutate,
    isPending: false,
    isError: false,
    error: null,
  }),
  useSubmitDecision: () => ({
    mutate: mockDecisionMutate,
    isPending: false,
    isError: false,
    error: null,
  }),
  useFeedback: () => ({
    mutate: mockFeedbackMutate,
    isPending: false,
    isError: false,
    error: null,
  }),
  useReviewField: () => ({
    mutate: mockReviewMutate,
    isPending: false,
  }),
}));

function renderPage(sessionId = 'test-session') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/verify/${sessionId}`]}>
        <Routes>
          <Route path="/verify/:sessionId" element={<ResultsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('ResultsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockVerificationData = createMockVerification({
      fields: [
        createMockField({ field_name: 'brand_name', declared_value: 'Test Brand', extracted_value: 'Test Brand' }),
        createMockField({ field_name: 'class_type', declared_value: 'Vodka', extracted_value: 'Vodka' }),
      ],
    });
    mockIsLoading = false;
    mockError = null;
  });

  it('renders overall status', () => {
    renderPage();
    expect(screen.getByText('Pass')).toBeInTheDocument();
  });

  it('renders comparison table with fields', () => {
    renderPage();
    expect(screen.getByText('Brand Name')).toBeInTheDocument();
    expect(screen.getByText('Class/Type')).toBeInTheDocument();
  });

  it('shows loading spinner while fetching', () => {
    mockIsLoading = true;
    mockVerificationData = undefined;
    renderPage();
    expect(screen.getByText('Loading results...')).toBeInTheDocument();
  });

  it('shows error message on fetch failure', () => {
    mockError = new Error('Server error');
    mockVerificationData = undefined;
    renderPage();
    expect(screen.getByText('Failed to load verification results.')).toBeInTheDocument();
  });

  it('renders Verification Results heading', () => {
    renderPage();
    expect(screen.getByText('Verification Results')).toBeInTheDocument();
  });

  it('renders Agent Decision section', () => {
    renderPage();
    expect(screen.getByText('Agent Decision')).toBeInTheDocument();
  });

  it('renders view mode toggle', () => {
    renderPage();
    expect(screen.getByText('Comparison Table')).toBeInTheDocument();
    expect(screen.getByText('Extracted Text')).toBeInTheDocument();
  });

  it('opens override modal on Override click', () => {
    renderPage();
    const overrideButtons = screen.getAllByText('Override');
    // Click the first Override button (in ComparisonRow, not AgentDecisionBar)
    fireEvent.click(overrideButtons[0]);
    expect(screen.getByText(/Override: Brand Name/)).toBeInTheDocument();
  });

  it('shows ReviewBanner when review_summary has flagged fields', () => {
    mockVerificationData = createMockVerification({
      review_summary: {
        total_fields: 8,
        fields_needing_review: 2,
        fields_reviewed: 0,
        flagged_field_names: ['alcohol_content'],
      },
      fields: [
        createMockField({ field_name: 'alcohol_content', status: 'extraction_uncertain' }),
      ],
    });
    renderPage();
    expect(screen.getByText(/requires review/)).toBeInTheDocument();
  });
});
