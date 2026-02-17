import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import OverrideModal from './OverrideModal';

describe('OverrideModal', () => {
  const defaultProps = {
    fieldName: 'brand_name',
    onSubmit: vi.fn(),
    onClose: vi.fn(),
  };

  it('renders field name in title', () => {
    render(<OverrideModal {...defaultProps} />);
    expect(screen.getByText('Override: Brand Name')).toBeInTheDocument();
  });

  it('renders status dropdown with all options', () => {
    render(<OverrideModal {...defaultProps} />);
    expect(screen.getByText('Match')).toBeInTheDocument();
    expect(screen.getByText('Content Mismatch')).toBeInTheDocument();
    expect(screen.getByText('Field Missing')).toBeInTheDocument();
  });

  it('calls onSubmit with selected status on Save Override', () => {
    const onSubmit = vi.fn();
    render(<OverrideModal {...defaultProps} onSubmit={onSubmit} />);

    // Change status to content_mismatch
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'content_mismatch' } });
    fireEvent.click(screen.getByText('Save Override'));

    expect(onSubmit).toHaveBeenCalledWith({
      override_status: 'content_mismatch',
      note: undefined,
    });
  });

  it('calls onSubmit with note when provided', () => {
    const onSubmit = vi.fn();
    render(<OverrideModal {...defaultProps} onSubmit={onSubmit} />);

    fireEvent.change(screen.getByPlaceholderText('Explain your override...'), {
      target: { value: 'Verified manually' },
    });
    fireEvent.click(screen.getByText('Save Override'));

    expect(onSubmit).toHaveBeenCalledWith({
      override_status: 'match',
      note: 'Verified manually',
    });
  });

  it('calls onClose on Cancel click', () => {
    const onClose = vi.fn();
    render(<OverrideModal {...defaultProps} onClose={onClose} />);
    fireEvent.click(screen.getByText('Cancel'));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('calls onClose on overlay click', () => {
    const onClose = vi.fn();
    render(<OverrideModal {...defaultProps} onClose={onClose} />);
    fireEvent.click(screen.getByRole('dialog'));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('does not close when clicking inside modal dialog', () => {
    const onClose = vi.fn();
    render(<OverrideModal {...defaultProps} onClose={onClose} />);
    fireEvent.click(screen.getByText('Override: Brand Name'));
    expect(onClose).not.toHaveBeenCalled();
  });

  it('has accessible modal role and aria attributes', () => {
    render(<OverrideModal {...defaultProps} />);
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAttribute('aria-labelledby', 'override-modal-title');
  });
});
