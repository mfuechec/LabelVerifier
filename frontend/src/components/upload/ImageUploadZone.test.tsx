import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import ImageUploadZone from './ImageUploadZone';

describe('ImageUploadZone', () => {
  const noop = vi.fn();

  it('renders the label text', () => {
    render(
      <ImageUploadZone label="Front Label" panelType="front" file={null} onFileSelect={noop} />
    );
    expect(screen.getByText('Front Label')).toBeInTheDocument();
  });

  it('shows drop hint when no file is selected', () => {
    render(
      <ImageUploadZone label="Front Label" panelType="front" file={null} onFileSelect={noop} />
    );
    expect(screen.getByText('Drop or click to browse')).toBeInTheDocument();
  });

  it('shows filename when a file is set', () => {
    const file = new File(['test'], 'label-photo.png', { type: 'image/png' });
    render(
      <ImageUploadZone label="Front Label" panelType="front" file={file} onFileSelect={noop} />
    );
    expect(screen.getByText('label-photo.png')).toBeInTheDocument();
  });
});
