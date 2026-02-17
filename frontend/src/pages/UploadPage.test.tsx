import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import UploadPage from './UploadPage';

const mockNavigate = vi.fn();
const mockMutateAsync = vi.fn();
const mockBatchMutateAsync = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../api/verifications', () => ({
  useVerify: () => ({
    mutateAsync: mockMutateAsync,
    isPending: false,
  }),
  useBatchUpload: () => ({
    mutateAsync: mockBatchMutateAsync,
    isPending: false,
  }),
  useBatchStatus: () => ({ data: undefined }),
}));

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <UploadPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('UploadPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders upload zone', () => {
    renderPage();
    expect(screen.getByText(/Drop COLA PDFs here/)).toBeInTheDocument();
  });

  it('shows "Verify Label" button by default', () => {
    renderPage();
    expect(screen.getByText('Verify Label')).toBeInTheDocument();
  });

  it('shows error when submitting with no files', async () => {
    renderPage();
    fireEvent.click(screen.getByText('Verify Label'));
    expect(screen.getByText('Please upload at least one COLA PDF.')).toBeInTheDocument();
  });

  it('navigates to results on single file verify success', async () => {
    mockMutateAsync.mockResolvedValueOnce({ session_id: 'test-123' });
    renderPage();

    // Simulate adding a file via the hidden input
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['pdf'], 'test.pdf', { type: 'application/pdf' });
    Object.defineProperty(input, 'files', { value: [file] });
    fireEvent.change(input);

    fireEvent.click(screen.getByText('Verify Label'));

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/verify/test-123');
    });
  });

  it('shows "Start Batch" for multiple files', () => {
    renderPage();

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const files = [
      new File(['pdf1'], 'a.pdf', { type: 'application/pdf' }),
      new File(['pdf2'], 'b.pdf', { type: 'application/pdf' }),
    ];
    Object.defineProperty(input, 'files', { value: files });
    fireEvent.change(input);

    expect(screen.getByText('Start Batch (2 PDFs)')).toBeInTheDocument();
  });

  it('shows file names after upload', () => {
    renderPage();

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['pdf'], 'my-cola.pdf', { type: 'application/pdf' });
    Object.defineProperty(input, 'files', { value: [file] });
    fireEvent.change(input);

    expect(screen.getByText('my-cola.pdf')).toBeInTheDocument();
  });

  it('removes file on Remove click', () => {
    renderPage();

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['pdf'], 'remove-me.pdf', { type: 'application/pdf' });
    Object.defineProperty(input, 'files', { value: [file] });
    fireEvent.change(input);

    expect(screen.getByText('remove-me.pdf')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Remove'));
    expect(screen.queryByText('remove-me.pdf')).not.toBeInTheDocument();
  });

  it('shows error banner on mutation failure', async () => {
    mockMutateAsync.mockRejectedValueOnce(new Error('Network error'));
    renderPage();

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['pdf'], 'test.pdf', { type: 'application/pdf' });
    Object.defineProperty(input, 'files', { value: [file] });
    fireEvent.change(input);

    fireEvent.click(screen.getByText('Verify Label'));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
  });
});
