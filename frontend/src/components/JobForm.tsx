import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api';
import { Job, AgentOverride } from '../types';

export function JobForm({ job, onClose }: { job: Job | null; onClose: () => void }) {
  const [name, setName] = useState(job?.name || '');
  const [description, setDesc] = useState(job?.description || '');
  const [plannerId, setPlannerId] = useState(job?.planner_agent_id || 0);
  const [coderId, setCoderId] = useState(job?.coder_agent_id || 0);
  const [testerId, setTesterId] = useState(job?.tester_agent_id || 0);
  const [loopMode, setLoopMode] = useState(job?.loop_mode || 'automatic');
  const [maxIterations, setMaxIterations] = useState(job?.max_iterations || 5);
  const [showOverrides, setShowOverrides] = useState(false);

  const overrides: Record<string, AgentOverride> = job?.agent_overrides || {};
  const [pTemp, setPTemp] = useState<number | null>(overrides.planner?.temperature ?? null);
  const [cTemp, setCTemp] = useState<number | null>(overrides.coder?.temperature ?? null);
  const [tTemp, setTTemp] = useState<number | null>(overrides.tester?.temperature ?? null);

  const { data: agents } = useQuery({ queryKey: ['agents'], queryFn: api.agents.list });
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: async () => {
      const agentOverrides: Record<string, AgentOverride> = {};
      if (pTemp !== null) agentOverrides.planner = { temperature: pTemp };
      if (cTemp !== null) agentOverrides.coder = { temperature: cTemp };
      if (tTemp !== null) agentOverrides.tester = { temperature: tTemp };
      const data: any = { name, description, planner_agent_id: plannerId, coder_agent_id: coderId, tester_agent_id: testerId, agent_overrides: agentOverrides, loop_mode: loopMode, max_iterations: maxIterations };
      if (job) return api.jobs.update(job.id, data);
      return api.jobs.create(data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
      onClose();
    },
  });

  const roleAgents = (role: string) => agents?.filter(a => a.role === role) || [];

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <h3 className="text-lg font-bold mb-4">{job ? 'Edit Job' : 'New Job'}</h3>
        <div className="flex flex-col gap-3">
          <div><label className="block text-sm font-medium mb-1">Name</label><input className="border rounded w-full px-3 py-2 text-sm" value={name} onChange={e => setName(e.target.value)} /></div>
          <div><label className="block text-sm font-medium mb-1">Description</label><input className="border rounded w-full px-3 py-2 text-sm" value={description} onChange={e => setDesc(e.target.value)} /></div>

          {(['planner', 'coder', 'tester'] as const).map((role, i) => (
            <div key={role}>
              <label className="block text-sm font-medium mb-1 capitalize">{role} Agent</label>
              <select className="border rounded w-full px-3 py-2 text-sm" value={[plannerId, coderId, testerId][i]} onChange={e => { const setter = [setPlannerId, setCoderId, setTesterId][i]; setter(parseInt(e.target.value)); }}>
                <option value={0}>-- Select --</option>
                {roleAgents(role).map(a => <option key={a.id} value={a.id}>{a.name} ({a.model_name})</option>)}
              </select>
            </div>
          ))}

          <div><label className="block text-sm font-medium mb-1">Loop Mode</label><select className="border rounded w-full px-3 py-2 text-sm" value={loopMode} onChange={e => setLoopMode(e.target.value as 'automatic' | 'manual')}><option value="automatic">Automatic</option><option value="manual">Manual</option></select></div>
          <div><label className="block text-sm font-medium mb-1">Max Iterations</label><input type="number" className="border rounded w-full px-3 py-2 text-sm" value={maxIterations} onChange={e => setMaxIterations(parseInt(e.target.value))} min={1} max={20} /></div>

          <button onClick={() => setShowOverrides(!showOverrides)} className="text-sm text-blue-600 hover:underline text-left">{showOverrides ? 'Hide' : 'Show'} Per-Agent Overrides</button>
          {showOverrides && (
            <div className="border rounded p-3 bg-gray-50 text-sm flex flex-col gap-2">
              {(['Planner', 'Coder', 'Tester'] as const).map((label, i) => {
                const entries: [number | null, (v: number | null) => void][] = [[pTemp, setPTemp], [cTemp, setCTemp], [tTemp, setTTemp]];
                const [temp, setTemp] = entries[i];
                return (
                  <div key={label}>
                    <label className="font-medium">{label} Temperature:</label>
                    <input type="number" className="border rounded px-2 py-1 text-sm w-24 ml-2" value={temp ?? ''} onChange={e => { const v = e.target.value; setTemp(v ? parseFloat(v) : null); }} step="0.1" min="0" max="2" placeholder="use default" />
                  </div>
                );
              })}
            </div>
          )}
        </div>
        <div className="flex gap-2 mt-4 justify-end">
          <button onClick={onClose} className="px-4 py-2 border rounded text-sm">Cancel</button>
          <button onClick={() => mutation.mutate()} disabled={!name || !plannerId || !coderId || !testerId} className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50">{job ? 'Save' : 'Create'}</button>
        </div>
        {mutation.isError && <p className="text-red-600 text-sm mt-2">Error: {(mutation.error as Error).message}</p>}
      </div>
    </div>
  );
}
