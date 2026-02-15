import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import ErrorBanner from './ErrorBanner';

describe('ErrorBanner', () => {
  it('renders message text', () => {
    render(<ErrorBanner message="Image too large" />);
    expect(screen.getByText('Image too large')).toBeInTheDocument();
  });

  it('has role="alert" for WCAG screen reader announcement', () => {
    render(<ErrorBanner message="Something went wrong" />);
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });
});
