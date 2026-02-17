import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import ComparisonTable from './ComparisonTable';
import { createMockField } from '../../test/utils';

describe('ComparisonTable', () => {
  const defaultProps = {
    highlightedField: null,
    onFieldHover: vi.fn(),
    onOverride: vi.fn(),
    onConfirmReview: vi.fn(),
  };

  it('renders a row for each field', () => {
    const fields = [
      createMockField({ field_name: 'brand_name' }),
      createMockField({ field_name: 'class_type' }),
      createMockField({ field_name: 'alcohol_content' }),
    ];
    render(<ComparisonTable fields={fields} {...defaultProps} />);
    expect(screen.getByText('Brand Name')).toBeInTheDocument();
    expect(screen.getByText('Class/Type')).toBeInTheDocument();
    expect(screen.getByText('Alcohol Content')).toBeInTheDocument();
  });

  it('renders table headers', () => {
    render(<ComparisonTable fields={[createMockField()]} {...defaultProps} />);
    expect(screen.getByText('Field')).toBeInTheDocument();
    expect(screen.getByText('Declared')).toBeInTheDocument();
    expect(screen.getByText('Extracted')).toBeInTheDocument();
    expect(screen.getByText('Status')).toBeInTheDocument();
    expect(screen.getByText('Confidence')).toBeInTheDocument();
    expect(screen.getByText('Action')).toBeInTheDocument();
  });

  it('passes highlightedField to the correct row', () => {
    const fields = [
      createMockField({ field_name: 'brand_name' }),
      createMockField({ field_name: 'class_type' }),
    ];
    const { container } = render(
      <ComparisonTable fields={fields} {...defaultProps} highlightedField="brand_name" />
    );
    const rows = container.querySelectorAll('tbody tr');
    expect(rows[0]?.className).toContain('highlighted');
    expect(rows[1]?.className).not.toContain('highlighted');
  });

  it('renders empty tbody when no fields', () => {
    const { container } = render(<ComparisonTable fields={[]} {...defaultProps} />);
    const rows = container.querySelectorAll('tbody tr');
    expect(rows.length).toBe(0);
  });
});
