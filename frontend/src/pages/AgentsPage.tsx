import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../api';
import { Agent, AgentRole } from '../types';
import { AgentForm } from '../components/AgentForm';

export function AgentsPage() {
  const [showForm, setShowForm] = useState(false);
  const [editAgent, setEditAgent] = useState<Agent | null>(null);
  const queryClient = useQueryClient();

  const { data: agents, isLoading } = useQuery({ queryKey: ['agents'], queryFn: api.agents.list });
  const deleteMutation = useMutation({
    mutationFn: api.agents.delete,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['agents'] }),
  });

  if (isLoading) return <div className="p-4">Loading...</div>;

  const roleColors: Record<AgentRole, string> = {
    planner: 'bg-blue-100 text-blue-800',
    coder: 'bg-green-100 text-green-800',
    tester: 'bg-orange-100 text-orange-800',
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-bold">Agent Library</h2>
        <button onClick={() => { setEditAgent(null); setShowForm(true); }} className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">+ New Agent</button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {agents?.map(agent => (
          <div key={agent.id} className="border rounded-lg p-4 hover:shadow-md transition">
            <div className="flex justify-between items-start mb-2">
              <h3 className="font-semibold">{agent.name}</h3>
              <span className={`text-xs px-2 py-0.5 rounded-full ${roleColors[agent.role]}`}>{agent.role}</span>
            </div>
            <p className="text-sm text-gray-500 mb-1">{agent.model_name}</p>
            <p className="text-xs text-gray-400 truncate">{agent.system_prompt.substring(0, 80)}...</p>
            <div className="flex gap-2 mt-3">
              <button onClick={() => { setEditAgent(agent); setShowForm(true); }} className="text-sm text-blue-600 hover:underline">Edit</button>
              <button onClick={() => { if (confirm('Delete this agent?')) deleteMutation.mutate(agent.id); }} className="text-sm text-red-600 hover:underline">Delete</button>
            </div>
          </div>
        ))}
      </div>

      {showForm && <AgentForm agent={editAgent} onClose={() => setShowForm(false)} />}
    </div>
  );
}
