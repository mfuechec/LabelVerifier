import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import ComparisonRow from './ComparisonRow';
import { createMockField } from '../../test/utils';

function renderRow(props: Partial<Parameters<typeof ComparisonRow>[0]> = {}) {
  const defaults = {
    field: createMockField(),
    isHighlighted: false,
    onHover: vi.fn(),
    onOverride: vi.fn(),
    onConfirmReview: vi.fn(),
    ...props,
  };
  return render(
    <table><tbody><ComparisonRow {...defaults} /></tbody></table>
  );
}

describe('ComparisonRow', () => {
  it('renders declared and extracted values', () => {
    renderRow({
      field: createMockField({ declared_value: 'Smirnoff', extracted_value: 'Smirnoff Vodka' }),
    });
    expect(screen.getByText('Smirnoff')).toBeInTheDocument();
    expect(screen.getByText('Smirnoff Vodka')).toBeInTheDocument();
  });

  it('renders field label from FIELD_LABELS', () => {
    renderRow({ field: createMockField({ field_name: 'brand_name' }) });
    expect(screen.getByText('Brand Name')).toBeInTheDocument();
  });

  it('renders dash for null declared value', () => {
    renderRow({ field: createMockField({ declared_value: null }) });
    // Should show "-" as fallback
    const cells = screen.getAllByText('-');
    expect(cells.length).toBeGreaterThanOrEqual(1);
  });

  it('shows Override button', () => {
    renderRow();
    expect(screen.getByText('Override')).toBeInTheDocument();
  });

  it('calls onOverride with field name on Override click', () => {
    const onOverride = vi.fn();
    renderRow({ onOverride, field: createMockField({ field_name: 'alcohol_content' }) });
    fireEvent.click(screen.getByText('Override'));
    expect(onOverride).toHaveBeenCalledWith('alcohol_content');
  });

  it('shows Confirm button for unreviewed extraction_uncertain fields', () => {
    renderRow({
      field: createMockField({ status: 'extraction_uncertain', reviewed: false }),
    });
    expect(screen.getByText('Confirm')).toBeInTheDocument();
  });

  it('calls onConfirmReview on Confirm click', () => {
    const onConfirmReview = vi.fn();
    renderRow({
      field: createMockField({ field_name: 'alcohol_content', status: 'extraction_uncertain', reviewed: false }),
      onConfirmReview,
    });
    fireEvent.click(screen.getByText('Confirm'));
    expect(onConfirmReview).toHaveBeenCalledWith('alcohol_content');
  });

  it('does not show Confirm for reviewed fields', () => {
    renderRow({
      field: createMockField({ status: 'extraction_uncertain', reviewed: true }),
    });
    expect(screen.queryByText('Confirm')).not.toBeInTheDocument();
  });

  it('does not show Confirm for non-uncertain fields', () => {
    renderRow({
      field: createMockField({ status: 'match', reviewed: false }),
    });
    expect(screen.queryByText('Confirm')).not.toBeInTheDocument();
  });

  it('applies highlighted class when isHighlighted is true', () => {
    const { container } = renderRow({ isHighlighted: true });
    const row = container.querySelector('tr');
    expect(row?.className).toContain('highlighted');
  });

  it('calls onHover on mouse enter/leave', () => {
    const onHover = vi.fn();
    const { container } = renderRow({ onHover, field: createMockField({ field_name: 'net_contents' }) });
    const row = container.querySelector('tr')!;
    fireEvent.mouseEnter(row);
    expect(onHover).toHaveBeenCalledWith('net_contents');
    fireEvent.mouseLeave(row);
    expect(onHover).toHaveBeenCalledWith(null);
  });
});
