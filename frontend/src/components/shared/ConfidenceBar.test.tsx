import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import ConfidenceBar from './ConfidenceBar';

describe('ConfidenceBar', () => {
  it('renders percentage text', () => {
    render(<ConfidenceBar value={92} />);
    expect(screen.getByText('92%')).toBeInTheDocument();
  });

  it('rounds percentage display', () => {
    render(<ConfidenceBar value={85.7} />);
    expect(screen.getByText('86%')).toBeInTheDocument();
  });

  it('uses green color for value >= 90', () => {
    const { container } = render(<ConfidenceBar value={95} />);
    const fill = container.querySelector('.confidence-bar-fill') as HTMLElement;
    expect(fill.style.backgroundColor).toBe('var(--emerald-600)');
  });

  it('uses yellow color for value >= 70 and < 90', () => {
    const { container } = render(<ConfidenceBar value={75} />);
    const fill = container.querySelector('.confidence-bar-fill') as HTMLElement;
    expect(fill.style.backgroundColor).toBe('var(--yellow-500)');
  });

  it('uses red color for value < 70', () => {
    const { container } = render(<ConfidenceBar value={50} />);
    const fill = container.querySelector('.confidence-bar-fill') as HTMLElement;
    expect(fill.style.backgroundColor).toBe('var(--red-600)');
  });

  it('sets bar width to match value', () => {
    const { container } = render(<ConfidenceBar value={80} />);
    const fill = container.querySelector('.confidence-bar-fill') as HTMLElement;
    expect(fill.style.width).toBe('80%');
  });

  it('caps bar width at 100%', () => {
    const { container } = render(<ConfidenceBar value={120} />);
    const fill = container.querySelector('.confidence-bar-fill') as HTMLElement;
    expect(fill.style.width).toBe('100%');
  });
});
