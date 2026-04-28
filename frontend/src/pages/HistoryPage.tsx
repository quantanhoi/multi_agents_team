import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../api';
import { Run } from '../types';

export function HistoryPage() {
  const { data: runs, isLoading } = useQuery({ queryKey: ['runs'], queryFn: () => api.runs.list() });
  const { data: jobs } = useQuery({ queryKey: ['jobs'], queryFn: api.jobs.list });
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const jobName = (id: number) => jobs?.find(j => j.id === id)?.name || `Job #${id}`;

  if (isLoading) return <div className="p-4">Loading...</div>;

  const statusColors: Record<string, string> = {
    done: 'bg-green-100 text-green-800', failed: 'bg-red-100 text-red-800',
    pending: 'bg-gray-100 text-gray-800', waiting_for_human: 'bg-yellow-100 text-yellow-800',
  };

  const duration = (r: Run) => {
    if (!r.completed_at) return '—';
    const d = (new Date(r.completed_at).getTime() - new Date(r.started_at).getTime()) / 1000;
    return d < 60 ? `${d.toFixed(0)}s` : `${(d/60).toFixed(1)}m`;
  };

  return (
    <div>
      <h2 className="text-xl font-bold mb-4">Run History</h2>
      {!runs || runs.length === 0 ? <p className="text-gray-500">No runs yet.</p> : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b text-left text-gray-500"><th className="p-2">Date</th><th className="p-2">Job</th><th className="p-2">Status</th><th className="p-2">Iterations</th><th className="p-2">Duration</th></tr></thead>
            <tbody>
              {runs.map(run => (
                <>
                  <tr key={run.id} className="border-b hover:bg-gray-50 cursor-pointer" onClick={() => setExpandedId(expandedId === run.id ? null : run.id)}>
                    <td className="p-2">{new Date(run.started_at).toLocaleString()}</td>
                    <td className="p-2">{jobName(run.job_id)}</td>
                    <td className="p-2"><span className={`px-2 py-0.5 rounded-full text-xs ${statusColors[run.status] || 'bg-gray-100'}`}>{run.status}</span></td>
                    <td className="p-2">{run.iterations}</td>
                    <td className="p-2">{duration(run)}</td>
                  </tr>
                  {expandedId === run.id && (
                    <tr key={`${run.id}-detail`}><td colSpan={5} className="p-4 bg-gray-50">
                      <div className="flex flex-col gap-3 text-sm">
                        <p><strong>Feature:</strong> {run.feature_request}</p>
                        {run.roadmap && (
                          <div><strong>Roadmap:</strong><pre className="text-xs mt-1 bg-white p-2 rounded border">{JSON.stringify(run.roadmap, null, 2)}</pre></div>
                        )}
                        <div className="grid grid-cols-2 gap-3">
                          <div><strong>Coder Outputs ({run.coder_outputs.length}):</strong><pre className="text-xs mt-1 bg-white p-2 rounded border max-h-64 overflow-y-auto">{JSON.stringify(run.coder_outputs, null, 2)}</pre></div>
                          <div><strong>Test Reports ({run.test_reports.length}):</strong><pre className="text-xs mt-1 bg-white p-2 rounded border max-h-64 overflow-y-auto">{JSON.stringify(run.test_reports, null, 2)}</pre></div>
                        </div>
                        {run.human_requests && run.human_requests.length > 0 && (
                          <div><strong>Human Interactions:</strong><pre className="text-xs mt-1 bg-white p-2 rounded border">{JSON.stringify(run.human_requests, null, 2)}</pre></div>
                        )}
                      </div>
                    </td></tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
