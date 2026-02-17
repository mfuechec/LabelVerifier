import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import LoadingSpinner from './LoadingSpinner';

describe('LoadingSpinner', () => {
  it('renders default "Processing..." message', () => {
    render(<LoadingSpinner />);
    expect(screen.getByText('Processing...')).toBeInTheDocument();
  });

  it('renders custom message', () => {
    render(<LoadingSpinner message="Loading results..." />);
    expect(screen.getByText('Loading results...')).toBeInTheDocument();
  });

  it('renders spinner element', () => {
    const { container } = render(<LoadingSpinner />);
    expect(container.querySelector('.spinner')).toBeInTheDocument();
  });
});
