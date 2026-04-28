import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, useEffect } from 'react';
import { api } from '../api';

export function SettingsPage() {
  const queryClient = useQueryClient();
  const { data: settings, isLoading } = useQuery({ queryKey: ['settings'], queryFn: api.settings.get });
  const [workingDir, setWorkingDir] = useState('');
  const [ollamaEndpoint, setOllamaEndpoint] = useState('');
  const [ollamaApiKey, setOllamaApiKey] = useState('');
  const [temperature, setTemperature] = useState(0.3);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (settings) {
      setWorkingDir(settings.working_dir);
      setOllamaEndpoint(settings.ollama_endpoint);
      setOllamaApiKey(settings.ollama_api_key || '');
      setTemperature(settings.default_temperature);
    }
  }, [settings]);

  const mutation = useMutation({
    mutationFn: () => api.settings.update({ working_dir: workingDir, ollama_endpoint: ollamaEndpoint, ollama_api_key: ollamaApiKey, default_temperature: temperature }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
  });

  if (isLoading) return <div className="p-4">Loading...</div>;

  return (
    <div className="max-w-lg">
      <h2 className="text-xl font-bold mb-4">Settings</h2>
      <div className="flex flex-col gap-4">
        <div><label className="block text-sm font-medium mb-1">Working Directory</label><input className="border rounded w-full px-3 py-2 text-sm" value={workingDir} onChange={e => setWorkingDir(e.target.value)} placeholder="/path/to/project" /></div>
        <div><label className="block text-sm font-medium mb-1">Ollama API Endpoint</label><input className="border rounded w-full px-3 py-2 text-sm" value={ollamaEndpoint} onChange={e => setOllamaEndpoint(e.target.value)} placeholder="http://localhost:11435" /></div>
        <div>
          <label className="block text-sm font-medium mb-1">Ollama API Key (Cloud)</label>
          <input type="password" className="border rounded w-full px-3 py-2 text-sm" value={ollamaApiKey} onChange={e => setOllamaApiKey(e.target.value)} placeholder="sk-... (leave empty for local Ollama)" />
          <p className="text-xs text-gray-400 mt-1">Used for model discovery. Per-agent keys override this.</p>
        </div>
        <div><label className="block text-sm font-medium mb-1">Default Temperature: {temperature}</label><input type="range" min="0" max="2" step="0.1" className="w-full" value={temperature} onChange={e => setTemperature(parseFloat(e.target.value))} /></div>
        <button onClick={() => mutation.mutate()} disabled={mutation.isPending} className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 disabled:opacity-50 self-start">
          {mutation.isPending ? 'Saving...' : saved ? 'Saved!' : 'Save Settings'}
        </button>
        {mutation.isError && <p className="text-red-600 text-sm">Error: {(mutation.error as Error).message}</p>}
      </div>
    </div>
  );
}
