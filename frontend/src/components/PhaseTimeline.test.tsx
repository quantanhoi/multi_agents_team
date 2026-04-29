import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PhaseTimeline } from './PhaseTimeline';
import { RunStatus } from '../types';

describe('PhaseTimeline', () => {
  const allPhases: RunStatus[] = ['planning_draft', 'planning_review_coder', 'planning_review_tester', 'planning_finalize', 'coding', 'testing', 'evaluating'];

  it('renders all phases', () => {
    render(<PhaseTimeline currentPhase="pending" completedPhases={[]} allPhases={allPhases} />);
    expect(screen.getByText('Draft')).toBeInTheDocument();
    expect(screen.getByText('Coding')).toBeInTheDocument();
    expect(screen.getByText('Evaluating')).toBeInTheDocument();
  });

  it('marks completed phases with checkmark', () => {
    render(<PhaseTimeline currentPhase="coding" completedPhases={['planning_draft', 'planning_review_coder']} allPhases={allPhases} />);
    expect(screen.getByText('Draft ✓')).toBeInTheDocument();
    expect(screen.getByText('Coder Review ✓')).toBeInTheDocument();
  });

  it('highlights current phase', () => {
    render(<PhaseTimeline currentPhase="coding" completedPhases={[]} allPhases={allPhases} />);
    const current = screen.getByText('Coding');
    expect(current).toBeInTheDocument();
    expect(current.className).toContain('bg-blue-200');
  });

  it('shows waiting badge when human input required', () => {
    render(<PhaseTimeline currentPhase="waiting_for_human" completedPhases={[]} allPhases={allPhases} />);
    expect(screen.getByText('⏳ Waiting for Human')).toBeInTheDocument();
  });
});
