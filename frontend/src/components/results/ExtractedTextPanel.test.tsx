import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import ExtractedTextPanel from './ExtractedTextPanel';
import { createMockField } from '../../test/utils';

describe('ExtractedTextPanel', () => {
  it('renders field labels', () => {
    const fields = [
      createMockField({ field_name: 'brand_name', extracted_value: 'Test Brand' }),
      createMockField({ field_name: 'class_type', extracted_value: 'Vodka' }),
    ];
    render(<ExtractedTextPanel fields={fields} highlightedField={null} onFieldClick={vi.fn()} />);
    expect(screen.getByText('Brand Name')).toBeInTheDocument();
    expect(screen.getByText('Class/Type')).toBeInTheDocument();
  });

  it('renders extracted text for each field', () => {
    const fields = [
      createMockField({ field_name: 'brand_name', extracted_value: 'Absolut Vodka' }),
    ];
    render(<ExtractedTextPanel fields={fields} highlightedField={null} onFieldClick={vi.fn()} />);
    expect(screen.getByText('Absolut Vodka')).toBeInTheDocument();
  });

  it('shows "Not found on label" for null extracted value', () => {
    const fields = [
      createMockField({ field_name: 'country_of_origin', extracted_value: null }),
    ];
    render(<ExtractedTextPanel fields={fields} highlightedField={null} onFieldClick={vi.fn()} />);
    expect(screen.getByText('Not found on label')).toBeInTheDocument();
  });

  it('calls onFieldClick when field card is clicked', () => {
    const onFieldClick = vi.fn();
    const fields = [createMockField({ field_name: 'brand_name' })];
    render(<ExtractedTextPanel fields={fields} highlightedField={null} onFieldClick={onFieldClick} />);
    fireEvent.click(screen.getByText('Brand Name'));
    expect(onFieldClick).toHaveBeenCalledWith('brand_name');
  });

  it('renders word diff for government_warning field', () => {
    const fields = [
      createMockField({
        field_name: 'government_warning',
        extracted_value: 'GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.',
      }),
    ];
    render(<ExtractedTextPanel fields={fields} highlightedField={null} onFieldClick={vi.fn()} />);
    expect(screen.getByText('Government Warning')).toBeInTheDocument();
  });

  it('shows confidence reason when available', () => {
    const fields = [
      createMockField({ field_name: 'brand_name', confidence_reason: 'Fuzzy match 95%' }),
    ];
    render(<ExtractedTextPanel fields={fields} highlightedField={null} onFieldClick={vi.fn()} />);
    expect(screen.getByText('Fuzzy match 95%')).toBeInTheDocument();
  });
});
