import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import ExtractionQualityBadge from './ExtractionQualityBadge';

describe('ExtractionQualityBadge', () => {
  it('renders "High" for high quality', () => {
    render(<ExtractionQualityBadge quality="high" />);
    expect(screen.getByText('High')).toBeInTheDocument();
  });

  it('renders "Medium" for medium quality', () => {
    render(<ExtractionQualityBadge quality="medium" />);
    expect(screen.getByText('Medium')).toBeInTheDocument();
  });

  it('renders "Low" for low quality', () => {
    render(<ExtractionQualityBadge quality="low" />);
    expect(screen.getByText('Low')).toBeInTheDocument();
  });

  it('returns null when quality is null', () => {
    const { container } = render(<ExtractionQualityBadge quality={null} />);
    expect(container.innerHTML).toBe('');
  });

  it('shows title with quality level', () => {
    render(<ExtractionQualityBadge quality="high" />);
    expect(screen.getByTitle('Extraction quality: High')).toBeInTheDocument();
  });
});
