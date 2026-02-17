import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import { createElement } from 'react';
import {
  useVerify,
  useVerification,
  useVerifications,
  useBatchUpload,
  useBatchStatus,
  useOverrideField,
  useSubmitDecision,
  useFeedback,
  useReviewField,
} from './verifications';

vi.mock('./client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
}));

import client from './client';

const mockedClient = vi.mocked(client);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

describe('useVerify', () => {
  beforeEach(() => vi.clearAllMocks());

  it('posts FormData and returns result', async () => {
    const mockResult = { session_id: 'abc', status: 'pass' };
    mockedClient.post.mockResolvedValueOnce({ data: { data: mockResult } });

    const { result } = renderHook(() => useVerify(), { wrapper: createWrapper() });

    const file = new File(['pdf'], 'test.pdf', { type: 'application/pdf' });
    result.current.mutate({ colaPdf: file });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockResult);
    expect(mockedClient.post).toHaveBeenCalledWith('/verify', expect.any(FormData));
  });
});

describe('useVerification', () => {
  beforeEach(() => vi.clearAllMocks());

  it('fetches verification by session ID', async () => {
    const mockResult = { session_id: 'abc', status: 'pass' };
    mockedClient.get.mockResolvedValueOnce({ data: { data: mockResult } });

    const { result } = renderHook(() => useVerification('abc'), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockResult);
    expect(mockedClient.get).toHaveBeenCalledWith('/verify/abc');
  });

  it('does not fetch when sessionId is undefined', () => {
    renderHook(() => useVerification(undefined), { wrapper: createWrapper() });
    expect(mockedClient.get).not.toHaveBeenCalled();
  });
});

describe('useVerifications', () => {
  beforeEach(() => vi.clearAllMocks());

  it('passes filter params to GET request', async () => {
    const mockResponse = { items: [], total: 0, page: 1, per_page: 20 };
    mockedClient.get.mockResolvedValueOnce({ data: { data: mockResponse } });

    const params = { status: 'pass', page: 1, per_page: 20 };
    const { result } = renderHook(() => useVerifications(params), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedClient.get).toHaveBeenCalledWith('/verifications', { params });
  });
});

describe('useBatchUpload', () => {
  beforeEach(() => vi.clearAllMocks());

  it('posts FormData with multiple PDFs', async () => {
    const mockResult = { batch_id: 'batch-1', total_items: 2, skipped_count: 0 };
    mockedClient.post.mockResolvedValueOnce({ data: { data: mockResult } });

    const { result } = renderHook(() => useBatchUpload(), { wrapper: createWrapper() });

    const files = [
      new File(['pdf1'], 'a.pdf', { type: 'application/pdf' }),
      new File(['pdf2'], 'b.pdf', { type: 'application/pdf' }),
    ];
    result.current.mutate({ colaPdfs: files });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockResult);
    expect(mockedClient.post).toHaveBeenCalledWith('/batch', expect.any(FormData));
  });
});

describe('useBatchStatus', () => {
  beforeEach(() => vi.clearAllMocks());

  it('fetches batch status by ID', async () => {
    const mockResult = { batch: { batch_id: 'b1', status: 'completed' }, items: [], skipped_items: [] };
    mockedClient.get.mockResolvedValueOnce({ data: { data: mockResult } });

    const { result } = renderHook(() => useBatchStatus('b1'), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockResult);
  });

  it('does not fetch when batchId is undefined', () => {
    renderHook(() => useBatchStatus(undefined), { wrapper: createWrapper() });
    expect(mockedClient.get).not.toHaveBeenCalled();
  });
});

describe('useOverrideField', () => {
  beforeEach(() => vi.clearAllMocks());

  it('patches field with override request', async () => {
    mockedClient.patch.mockResolvedValueOnce({});

    const { result } = renderHook(() => useOverrideField(), { wrapper: createWrapper() });

    result.current.mutate({
      sessionId: 'abc',
      fieldName: 'brand_name',
      body: { override_status: 'match', note: 'Correct' },
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedClient.patch).toHaveBeenCalledWith('/verify/abc/fields/brand_name', {
      override_status: 'match',
      note: 'Correct',
    });
  });
});

describe('useSubmitDecision', () => {
  beforeEach(() => vi.clearAllMocks());

  it('posts decision', async () => {
    mockedClient.post.mockResolvedValueOnce({});

    const { result } = renderHook(() => useSubmitDecision(), { wrapper: createWrapper() });

    result.current.mutate({
      sessionId: 'abc',
      body: { decision: 'confirmed', notes: 'Looks good' },
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedClient.post).toHaveBeenCalledWith('/verify/abc/decision', {
      decision: 'confirmed',
      notes: 'Looks good',
    });
  });
});

describe('useReviewField', () => {
  beforeEach(() => vi.clearAllMocks());

  it('posts review for a field', async () => {
    mockedClient.post.mockResolvedValueOnce({});

    const { result } = renderHook(() => useReviewField(), { wrapper: createWrapper() });

    result.current.mutate({ sessionId: 'abc', fieldName: 'alcohol_content' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedClient.post).toHaveBeenCalledWith('/verify/abc/fields/alcohol_content/review');
  });
});

describe('useFeedback', () => {
  beforeEach(() => vi.clearAllMocks());

  it('posts feedback', async () => {
    mockedClient.post.mockResolvedValueOnce({});

    const { result } = renderHook(() => useFeedback(), { wrapper: createWrapper() });

    result.current.mutate({
      sessionId: 'abc',
      body: { ai_correct: true },
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedClient.post).toHaveBeenCalledWith('/verify/abc/feedback', { ai_correct: true });
  });
});
