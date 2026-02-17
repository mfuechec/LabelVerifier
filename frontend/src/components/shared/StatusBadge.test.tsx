import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import StatusBadge from './StatusBadge';

describe('StatusBadge', () => {
  it.each([
    ['match', 'Match'],
    ['content_mismatch', 'Mismatch'],
    ['field_missing', 'Missing'],
    ['extraction_uncertain', 'Uncertain'],
    ['pass', 'Pass'],
    ['needs_review', 'Needs Review'],
    ['fail', 'Fail'],
    ['pending', 'Pending'],
  ])('renders label "%s" as "%s"', (status, expectedLabel) => {
    render(<StatusBadge status={status} />);
    expect(screen.getByText(expectedLabel)).toBeInTheDocument();
  });

  it('falls back to raw status string for unknown status', () => {
    render(<StatusBadge status="unknown_status" />);
    expect(screen.getByText('unknown_status')).toBeInTheDocument();
  });

  it.each([
    ['match', 'badge-match'],
    ['content_mismatch', 'badge-mismatch'],
    ['field_missing', 'badge-missing'],
    ['extraction_uncertain', 'badge-uncertain'],
    ['pass', 'badge-pass'],
    ['needs_review', 'badge-needs-review'],
    ['fail', 'badge-fail'],
    ['pending', 'badge-pending'],
  ])('applies CSS class for status "%s"', (status, expectedClass) => {
    const { container } = render(<StatusBadge status={status} />);
    const badge = container.querySelector('span');
    expect(badge?.className).toContain(expectedClass);
  });

  it('applies sm size class', () => {
    const { container } = render(<StatusBadge status="match" size="sm" />);
    expect(container.querySelector('span')?.className).toContain('badge-sm');
  });

  it('applies lg size class', () => {
    const { container } = render(<StatusBadge status="match" size="lg" />);
    expect(container.querySelector('span')?.className).toContain('badge-lg');
  });

  it('uses no size class for default md', () => {
    const { container } = render(<StatusBadge status="match" />);
    const className = container.querySelector('span')?.className ?? '';
    expect(className).not.toContain('badge-sm');
    expect(className).not.toContain('badge-lg');
  });
});
