import { useState } from 'react';
import { RunStep } from '../types';

export default function ActiveStepPanel({
  step,
  stream,
  onOverride,
}: {
  step: Partial<RunStep> & { model?: string };
  stream?: string;
  onOverride: (text: string) => void;
}) {
  const [override, setOverride] = useState('');
  return (
    <div className="border rounded-lg p-4 bg-white shadow-sm">
      <div className="flex items-center gap-2 mb-2">
        <span className="px-2 py-1 rounded bg-blue-100 text-blue-800 text-sm font-semibold">
          {(step.agent || step.step_type || 'WAITING').toUpperCase()}
        </span>
        <span className="text-xs text-gray-500">Step {step.step_number ?? '-'}</span>
        {step.model && <span className="text-xs text-gray-400">model: {step.model}</span>}
      </div>
      <div className="whitespace-pre-wrap text-sm bg-gray-50 rounded p-3 min-h-[120px] max-h-[400px] overflow-y-auto">
        {stream || step.output?.raw_output || 'Waiting for output...'}
      </div>
      <div className="mt-3 flex gap-2">
        <input
          className="flex-1 border rounded px-3 py-1 text-sm"
          placeholder="Type override / hint..."
          value={override}
          onChange={(e) => setOverride(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') { onOverride(override); setOverride(''); }
          }}
        />
        <button
          className="px-3 py-1 bg-gray-800 text-white rounded text-sm"
          onClick={() => { onOverride(override); setOverride(''); }}
        >Send</button>
      </div>
    </div>
  );
}
