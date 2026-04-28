import { RunStatus } from '../types';

export function PhaseTimeline({ currentPhase, completedPhases, allPhases }: {
  currentPhase: RunStatus; completedPhases: RunStatus[]; allPhases: RunStatus[];
}) {
  const phaseLabels: Record<string, string> = {
    planning_draft: 'Draft', planning_review_coder: 'Coder Review', planning_review_tester: 'Tester Review',
    planning_finalize: 'Finalize', coding: 'Coding', testing: 'Testing', evaluating: 'Evaluating',
    done: 'Done', failed: 'Failed', waiting_for_human: 'Waiting',
  };

  return (
    <div className="flex flex-wrap gap-2 mb-4">
      {allPhases.map(phase => {
        const isComplete = completedPhases.includes(phase);
        const isCurrent = currentPhase === phase;
        const baseClass = 'px-3 py-1 rounded-full text-xs font-medium transition';
        if (isComplete) return <span key={phase} className={`${baseClass} bg-green-200 text-green-800`}>{phaseLabels[phase] || phase} ✓</span>;
        if (isCurrent) return <span key={phase} className={`${baseClass} bg-blue-200 text-blue-800 animate-pulse`}>{phaseLabels[phase] || phase}</span>;
        return <span key={phase} className={`${baseClass} bg-gray-100 text-gray-400 border`}>{phaseLabels[phase] || phase}</span>;
      })}
      {currentPhase === 'waiting_for_human' && (
        <span className="px-3 py-1 rounded-full text-xs font-medium bg-yellow-200 text-yellow-800 animate-pulse">⏳ Waiting for Human</span>
      )}
    </div>
  );
}
