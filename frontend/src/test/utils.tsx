import { render, type RenderOptions } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement, ReactNode } from 'react';
import type { FieldComparisonResult, HistoryItem, VerificationResult, ReviewSummary } from '../api/types';

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

interface WrapperOptions {
  initialEntries?: string[];
}

function createWrapper({ initialEntries = ['/'] }: WrapperOptions = {}) {
  const queryClient = createTestQueryClient();
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={initialEntries}>
          {children}
        </MemoryRouter>
      </QueryClientProvider>
    );
  };
}

export function renderWithProviders(
  ui: ReactElement,
  options?: Omit<RenderOptions, 'wrapper'> & WrapperOptions
) {
  const { initialEntries, ...renderOptions } = options ?? {};
  return render(ui, {
    wrapper: createWrapper({ initialEntries }),
    ...renderOptions,
  });
}

export function createMockField(overrides: Partial<FieldComparisonResult> = {}): FieldComparisonResult {
  return {
    field_name: 'brand_name',
    declared_value: 'Test Brand',
    extracted_value: 'Test Brand',
    status: 'match',
    confidence: 95,
    match_strategy: 'fuzzy',
    bounding_box: null,
    extraction_confidence: 'high',
    confidence_reason: null,
    reviewed: false,
    ...overrides,
  };
}

export function createMockReviewSummary(overrides: Partial<ReviewSummary> = {}): ReviewSummary {
  return {
    total_fields: 8,
    fields_needing_review: 2,
    fields_reviewed: 0,
    flagged_field_names: ['alcohol_content', 'government_warning'],
    ...overrides,
  };
}

export function createMockVerification(overrides: Partial<VerificationResult> = {}): VerificationResult {
  return {
    session_id: 'test-session-123',
    status: 'pass',
    overall_confidence: 92.5,
    beverage_type: 'distilled_spirits',
    fields: [
      createMockField(),
      createMockField({ field_name: 'class_type', declared_value: 'Vodka', extracted_value: 'Vodka' }),
    ],
    annotated_images: {},
    created_at: '2026-02-17T12:00:00Z',
    review_summary: null,
    compliance_issues: [],
    ...overrides,
  };
}

export function createMockHistoryItem(overrides: Partial<HistoryItem> = {}): HistoryItem {
  return {
    session_id: 'hist-session-001',
    application_id: 'APP-001',
    brand_name: 'Test Brand',
    beverage_type: 'distilled_spirits',
    status: 'pass',
    overall_confidence: 91,
    agent_decision: 'confirmed',
    created_at: '2026-02-17T10:00:00Z',
    processing_time_ms: 4500,
    total_tokens: 12500,
    estimated_cost_usd: 0.0125,
    ...overrides,
  };
}
