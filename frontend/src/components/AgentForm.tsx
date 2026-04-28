import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api';
import { Agent, AgentRole } from '../types';

const DEFAULT_PROMPTS: Record<AgentRole, string> = {
  planner:
    'You are the planner. Your job is to break work into small phases and produce a roadmap. Do not write code. Return JSON only with: goal, roadmap (array of phases with name, tasks, definition_of_done for both coder and tester), files_needed, risks, human_input_request (null or object).',
  coder:
    'You are the coder. Write or edit code only from the approved plan. Do not change unrelated files. Return JSON only with: summary, files_changed, patch_or_full_files (array of {path, content}), notes_for_tester, human_input_request (null or object).',
  tester:
    'You are the tester. Review the code and test outputs. Find bugs, edge cases, and missing tests. Return JSON only with: status (pass|fail), bugs (array of {severity, description, file}), definition_of_done_check (for_coder, for_tester), manual_test_checklist, automation_gaps, next_action (fix_bugs|continue|done), human_input_request (null or object).',
};

function formatSize(bytes: number): string {
  if (!bytes) return '?';
  if (bytes < 1e9) return `${(bytes / 1e6).toFixed(0)} MB`;
  return `${(bytes / 1e9).toFixed(1)} GB`;
}

export function AgentForm({ agent, onClose }: { agent: Agent | null; onClose: () => void }) {
  const [name, setName] = useState(agent?.name || '');
  const [role, setRole] = useState<AgentRole>(agent?.role || 'coder');
  const [modelName, setModelName] = useState(agent?.model_name || '');
  const [systemPrompt, setSystemPrompt] = useState(agent?.system_prompt || DEFAULT_PROMPTS['coder']);
  const [temperature, setTemperature] = useState(agent?.temperature ?? 0.3);
  const [endpoint, setEndpoint] = useState(agent?.ollama_endpoint || 'http://localhost:11435');
  const [apiKey, setApiKey] = useState(agent?.api_key || '');

  const [models, setModels] = useState<{ name: string; size: number; digest: string }[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState('');

  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: async () => {
      const data = { name, role, model_name: modelName, system_prompt: systemPrompt, temperature, ollama_endpoint: endpoint, api_key: apiKey };
      if (agent) return api.agents.update(agent.id, data);
      return api.agents.create(data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] });
      onClose();
    },
  });

  const discoverModels = async () => {
    setModelsLoading(true);
    setModelsError('');
    try {
      const list = await api.ollama.models();
      setModels(list);
    } catch (e) {
      setModelsError((e as Error).message);
    }
    setModelsLoading(false);
  };

  const applyModel = (selectedModel: string) => {
    setModelName(selectedModel);
    const baseName = selectedModel.split(':')[0];
    const roleLabel = role.charAt(0).toUpperCase() + role.slice(1);
    if (!agent) {
      setName(`${baseName.charAt(0).toUpperCase() + baseName.slice(1)} ${roleLabel}`);
      setSystemPrompt(DEFAULT_PROMPTS[role]);
    }
  };

  const handleRoleChange = (newRole: AgentRole) => {
    setRole(newRole);
    if (!agent && !systemPrompt) {
      setSystemPrompt(DEFAULT_PROMPTS[newRole]);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <h3 className="text-lg font-bold mb-4">{agent ? 'Edit Agent' : 'New Agent'}</h3>

        <div className="flex flex-col gap-3">
          {/* Model Discovery */}
          <div className="border rounded-lg p-3 bg-gray-50">
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm font-medium">Ollama Models</span>
              <button
                onClick={discoverModels}
                disabled={modelsLoading}
                className="text-xs px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
              >
                {modelsLoading ? 'Discovering...' : 'Discover Models'}
              </button>
            </div>
            {modelsError && <p className="text-xs text-red-600 mb-2">{modelsError}</p>}
            {models.length > 0 && (
              <select
                className="border rounded w-full px-3 py-2 text-sm"
                value={modelName}
                onChange={e => applyModel(e.target.value)}
              >
                <option value="">-- Pick a model --</option>
                {models.map(m => (
                  <option key={m.name} value={m.name}>
                    {m.name} ({formatSize(m.size)})
                  </option>
                ))}
              </select>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">Name</label>
            <input className="border rounded w-full px-3 py-2 text-sm" value={name} onChange={e => setName(e.target.value)} />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Role</label>
            <select className="border rounded w-full px-3 py-2 text-sm" value={role} onChange={e => handleRoleChange(e.target.value as AgentRole)}>
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
          <div>
            <label className="block text-sm font-medium mb-1">API Key (Ollama Cloud)</label>
            <input type="password" className="border rounded w-full px-3 py-2 text-sm" placeholder="sk-... (leave empty for local Ollama)" value={apiKey} onChange={e => setApiKey(e.target.value)} />
            <p className="text-xs text-gray-400 mt-1">Required for Ollama Cloud. Leave empty for local Ollama.</p>
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
