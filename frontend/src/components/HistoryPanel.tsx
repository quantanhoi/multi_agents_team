import { useState } from 'react';
import { RunStep } from '../types';

export default function HistoryPanel({ steps }: { steps: RunStep[] }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div className="border rounded-lg overflow-hidden">
      <div className="bg-gray-100 px-4 py-2 font-medium text-sm">History</div>
      <div className="max-h-[300px] overflow-y-auto">
        {steps.length === 0 && (
          <div className="px-4 py-3 text-sm text-gray-400">No steps yet</div>
        )}
        {steps.map((s) => (
          <div key={s.step_number} className="border-b last:border-0">
            <button
              className="w-full text-left px-4 py-2 text-sm hover:bg-gray-50 flex justify-between"
              onClick={() => setOpen(open === s.step_number ? null : s.step_number)}
            >
              <span>Step {s.step_number}: {s.agent}</span>
              <span className="text-gray-400">{s.step_type}</span>
            </button>
            {open === s.step_number && (
              <div className="px-4 pb-3 text-xs text-gray-600 whitespace-pre-wrap">
                {JSON.stringify(s.output, null, 2)}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
