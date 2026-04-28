import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api';
import { Run, RunContext } from '../types';

export function ContextBuilder({ onRunStart }: { onRunStart: (run: Run) => void }) {
  const [jobId, setJobId] = useState<number>(0);
  const [featureRequest, setFeatureRequest] = useState('');
  const [files, setFiles] = useState('');
  const [bugs, setBugs] = useState('');
  const [constraints, setConstraints] = useState('');
  const [extraNotes, setExtraNotes] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const { data: jobs } = useQuery({ queryKey: ['jobs'], queryFn: api.jobs.list });

  const handleRun = async () => {
    if (!jobId || !featureRequest.trim()) {
      setError('Job and feature request are required');
      return;
    }
    setError('');
    setLoading(true);
    try {
      const context: RunContext = {
        selected_files: files.split(',').map(f => f.trim()).filter(Boolean),
        known_bugs: bugs.split('\n').filter(Boolean),
        constraints: constraints.split('\n').filter(Boolean),
        extra_notes: extraNotes,
      };
      const run = await api.runs.start(jobId, featureRequest, context);
      onRunStart(run);
    } catch (e) {
      setError((e as Error).message);
    }
    setLoading(false);
  };

  return (
    <div className="max-w-2xl">
      <h2 className="text-xl font-bold mb-4">Run Job</h2>
      <div className="flex flex-col gap-3">
        <div>
          <label className="block text-sm font-medium mb-1">Job</label>
          <select className="border rounded w-full px-3 py-2 text-sm" value={jobId} onChange={e => setJobId(parseInt(e.target.value))}>
            <option value={0}>-- Select a job --</option>
            {jobs?.map(j => <option key={j.id} value={j.id}>{j.name}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Feature Request</label>
          <textarea className="border rounded w-full px-3 py-2 text-sm" rows={4} value={featureRequest} onChange={e => setFeatureRequest(e.target.value)} placeholder="Describe what you want built..." />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Files (comma-separated paths)</label>
          <input className="border rounded w-full px-3 py-2 text-sm" value={files} onChange={e => setFiles(e.target.value)} placeholder="src/app.py, src/models.py" />
          <p className="text-xs text-gray-500 mt-1">
            Paths are relative to the <strong>Working Directory</strong> set in <a href="#/settings" className="text-blue-600 underline">Settings</a>.
            If using Docker, set <code>PROJECT_DIR</code> in <code>.env</code> and use <code>/workspace</code> as Working Directory.
          </p>
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Known Bugs (one per line)</label>
          <textarea className="border rounded w-full px-3 py-2 text-sm" rows={3} value={bugs} onChange={e => setBugs(e.target.value)} />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Constraints (one per line)</label>
          <textarea className="border rounded w-full px-3 py-2 text-sm" rows={3} value={constraints} onChange={e => setConstraints(e.target.value)} />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Extra Notes</label>
          <textarea className="border rounded w-full px-3 py-2 text-sm" rows={2} value={extraNotes} onChange={e => setExtraNotes(e.target.value)} />
        </div>
      </div>
      {error && <p className="text-red-600 text-sm mt-2">{error}</p>}
      <button onClick={handleRun} disabled={loading} className="mt-4 px-6 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50">
        {loading ? 'Starting...' : 'Run'}
      </button>
    </div>
  );
}
