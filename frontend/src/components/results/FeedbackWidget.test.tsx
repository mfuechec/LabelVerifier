import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import FeedbackWidget from './FeedbackWidget';

describe('FeedbackWidget', () => {
  it('renders feedback question', () => {
    render(<FeedbackWidget onFeedback={vi.fn()} isSubmitting={false} />);
    expect(screen.getByText('Was the AI analysis correct?')).toBeInTheDocument();
  });

  it('shows thank you message after clicking AI Correct', async () => {
    const user = userEvent.setup();
    const onFeedback = vi.fn();
    render(<FeedbackWidget onFeedback={onFeedback} isSubmitting={false} />);

    await user.click(screen.getByText('AI Correct'));

    expect(onFeedback).toHaveBeenCalledWith(true);
    expect(screen.getByText('Thank you for your feedback!')).toBeInTheDocument();
  });

  it('shows thank you message after clicking AI Incorrect', async () => {
    const user = userEvent.setup();
    const onFeedback = vi.fn();
    render(<FeedbackWidget onFeedback={onFeedback} isSubmitting={false} />);

    await user.click(screen.getByText('AI Incorrect'));

    expect(onFeedback).toHaveBeenCalledWith(false);
    expect(screen.getByText('Thank you for your feedback!')).toBeInTheDocument();
  });
});
