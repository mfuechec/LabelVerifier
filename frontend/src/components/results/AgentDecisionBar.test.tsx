import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import AgentDecisionBar from './AgentDecisionBar';

describe('AgentDecisionBar', () => {
  const defaultProps = {
    onDecision: vi.fn(),
    onFeedback: vi.fn(),
    isSubmitting: false,
  };

  it('renders confirm and override buttons', () => {
    render(<AgentDecisionBar {...defaultProps} />);
    expect(screen.getByText('Confirm AI Result')).toBeInTheDocument();
    expect(screen.getByText('Override')).toBeInTheDocument();
  });

  it('calls onDecision("confirmed") and onFeedback(true) on confirm', () => {
    const onDecision = vi.fn();
    const onFeedback = vi.fn();
    render(<AgentDecisionBar {...defaultProps} onDecision={onDecision} onFeedback={onFeedback} />);

    fireEvent.click(screen.getByText('Confirm AI Result'));

    expect(onDecision).toHaveBeenCalledWith('confirmed', undefined);
    expect(onFeedback).toHaveBeenCalledWith(true);
  });

  it('shows success message after confirm', () => {
    render(<AgentDecisionBar {...defaultProps} />);
    fireEvent.click(screen.getByText('Confirm AI Result'));
    expect(screen.getByText(/Decision recorded/)).toBeInTheDocument();
  });

  it('shows notes textarea on first Override click', () => {
    render(<AgentDecisionBar {...defaultProps} />);
    fireEvent.click(screen.getByText('Override'));
    expect(screen.getByPlaceholderText(/Add notes for your override/)).toBeInTheDocument();
  });

  it('shows "Submit Override" button after first Override click', () => {
    render(<AgentDecisionBar {...defaultProps} />);
    fireEvent.click(screen.getByText('Override'));
    expect(screen.getByText('Submit Override')).toBeInTheDocument();
  });

  it('calls onDecision("overridden") and onFeedback(false) on override submit', () => {
    const onDecision = vi.fn();
    const onFeedback = vi.fn();
    render(<AgentDecisionBar {...defaultProps} onDecision={onDecision} onFeedback={onFeedback} />);

    // First click shows notes
    fireEvent.click(screen.getByText('Override'));
    // Type notes
    fireEvent.change(screen.getByPlaceholderText(/Add notes for your override/), {
      target: { value: 'Wrong brand' },
    });
    // Second click submits
    fireEvent.click(screen.getByText('Submit Override'));

    expect(onDecision).toHaveBeenCalledWith('overridden', 'Wrong brand');
    expect(onFeedback).toHaveBeenCalledWith(false);
  });

  it('disables buttons when isSubmitting is true', () => {
    render(<AgentDecisionBar {...defaultProps} isSubmitting={true} />);
    expect(screen.getByText('Confirm AI Result')).toBeDisabled();
    expect(screen.getByText('Override')).toBeDisabled();
  });
});
