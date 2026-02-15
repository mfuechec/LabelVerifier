import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import OverallStatus from './OverallStatus';

describe('OverallStatus', () => {
  it('renders confidence percentage', () => {
    render(<OverallStatus status="pass" confidence={92.5} beverageType="wine" />);
    expect(screen.getByText('93%')).toBeInTheDocument();
  });

  it('renders beverage type label', () => {
    render(<OverallStatus status="pass" confidence={85} beverageType="distilled_spirits" />);
    expect(screen.getByText('Distilled Spirits')).toBeInTheDocument();
  });
});
