import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api';
import { Agent, AgentRole } from '../types';

export function AgentForm({ agent, onClose }: { agent: Agent | null; onClose: () => void }) {
  const [name, setName] = useState(agent?.name || '');
  const [role, setRole] = useState<AgentRole>(agent?.role || 'coder');
  const [modelName, setModelName] = useState(agent?.model_name || '');
  const [systemPrompt, setSystemPrompt] = useState(agent?.system_prompt || '');
  const [temperature, setTemperature] = useState(agent?.temperature ?? 0.3);
  const [endpoint, setEndpoint] = useState(agent?.ollama_endpoint || 'http://localhost:11434');

  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: async () => {
      const data = { name, role, model_name: modelName, system_prompt: systemPrompt, temperature, ollama_endpoint: endpoint };
      if (agent) return api.agents.update(agent.id, data);
      return api.agents.create(data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] });
      onClose();
    },
  });

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <h3 className="text-lg font-bold mb-4">{agent ? 'Edit Agent' : 'New Agent'}</h3>
        <div className="flex flex-col gap-3">
          <div>
            <label className="block text-sm font-medium mb-1">Name</label>
            <input className="border rounded w-full px-3 py-2 text-sm" value={name} onChange={e => setName(e.target.value)} />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Role</label>
            <select className="border rounded w-full px-3 py-2 text-sm" value={role} onChange={e => setRole(e.target.value as AgentRole)}>
              <option value="planner">Planner</option>
              <option value="coder">Coder</option>
              <option value="tester">Tester</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Model Name</label>
            <input className="border rounded w-full px-3 py-2 text-sm" placeholder="e.g. kimi-k2.6" value={modelName} onChange={e => setModelName(e.target.value)} />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">System Prompt</label>
            <textarea className="border rounded w-full px-3 py-2 text-sm" rows={6} value={systemPrompt} onChange={e => setSystemPrompt(e.target.value)} />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Temperature: {temperature}</label>
            <input type="range" min="0" max="2" step="0.1" className="w-full" value={temperature} onChange={e => setTemperature(parseFloat(e.target.value))} />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Ollama Endpoint</label>
            <input className="border rounded w-full px-3 py-2 text-sm" value={endpoint} onChange={e => setEndpoint(e.target.value)} />
          </div>
        </div>
        <div className="flex gap-2 mt-4 justify-end">
          <button onClick={onClose} className="px-4 py-2 border rounded text-sm">Cancel</button>
          <button onClick={() => mutation.mutate()} disabled={!name || !modelName} className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50">
            {agent ? 'Save' : 'Create'}
          </button>
        </div>
        {mutation.isError && <p className="text-red-600 text-sm mt-2">Error: {(mutation.error as Error).message}</p>}
      </div>
    </div>
  );
}
