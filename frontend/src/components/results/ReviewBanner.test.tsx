import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import ReviewBanner from './ReviewBanner';
import { createMockReviewSummary } from '../../test/utils';

describe('ReviewBanner', () => {
  it('shows remaining review count', () => {
    const summary = createMockReviewSummary({ fields_needing_review: 3, fields_reviewed: 1 });
    render(<ReviewBanner reviewSummary={summary} onReviewNext={vi.fn()} />);
    expect(screen.getByText(/2 of 3 flagged fields need attention/)).toBeInTheDocument();
  });

  it('calls onReviewNext when button clicked', () => {
    const onReviewNext = vi.fn();
    const summary = createMockReviewSummary({ fields_needing_review: 2, fields_reviewed: 0 });
    render(<ReviewBanner reviewSummary={summary} onReviewNext={onReviewNext} />);
    fireEvent.click(screen.getByText('Review Next'));
    expect(onReviewNext).toHaveBeenCalledOnce();
  });

  it('hides Review Next button when all fields reviewed', () => {
    const summary = createMockReviewSummary({ fields_needing_review: 2, fields_reviewed: 2 });
    render(<ReviewBanner reviewSummary={summary} onReviewNext={vi.fn()} />);
    expect(screen.queryByText('Review Next')).not.toBeInTheDocument();
  });

  it('shows completion message when all reviewed', () => {
    const summary = createMockReviewSummary({ fields_needing_review: 2, fields_reviewed: 2 });
    render(<ReviewBanner reviewSummary={summary} onReviewNext={vi.fn()} />);
    expect(screen.getByText(/All fields reviewed/)).toBeInTheDocument();
  });

  it('returns null when fields_needing_review is 0', () => {
    const summary = createMockReviewSummary({ fields_needing_review: 0, fields_reviewed: 0 });
    const { container } = render(<ReviewBanner reviewSummary={summary} onReviewNext={vi.fn()} />);
    expect(container.innerHTML).toBe('');
  });

  it('shows progress count', () => {
    const summary = createMockReviewSummary({ fields_needing_review: 4, fields_reviewed: 1 });
    render(<ReviewBanner reviewSummary={summary} onReviewNext={vi.fn()} />);
    expect(screen.getByText('1/4 reviewed')).toBeInTheDocument();
  });
});
