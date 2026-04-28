import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../api';
import { Job } from '../types';
import { JobForm } from '../components/JobForm';

export function JobsPage() {
  const [showForm, setShowForm] = useState(false);
  const [editJob, setEditJob] = useState<Job | null>(null);
  const queryClient = useQueryClient();

  const { data: jobs, isLoading } = useQuery({ queryKey: ['jobs'], queryFn: api.jobs.list });
  const { data: agents } = useQuery({ queryKey: ['agents'], queryFn: api.agents.list });
  const deleteMutation = useMutation({
    mutationFn: api.jobs.delete,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['jobs'] }),
  });

  const agentName = (id: number) => agents?.find(a => a.id === id)?.name || `Agent #${id}`;

  if (isLoading) return <div className="p-4">Loading...</div>;

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-bold">Jobs</h2>
        <button onClick={() => { setEditJob(null); setShowForm(true); }} className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">+ New Job</button>
      </div>

      <div className="flex flex-col gap-3">
        {jobs?.map(job => (
          <div key={job.id} className="border rounded-lg p-4 flex justify-between items-center">
            <div>
              <h3 className="font-semibold">{job.name}</h3>
              <p className="text-xs text-gray-500">
                P: {agentName(job.planner_agent_id)} | C: {agentName(job.coder_agent_id)} | T: {agentName(job.tester_agent_id)}
              </p>
            </div>
            <div className="flex items-center gap-3">
              <span className={`text-xs px-2 py-1 rounded-full ${job.loop_mode === 'automatic' ? 'bg-purple-100 text-purple-800' : 'bg-yellow-100 text-yellow-800'}`}>
                {job.loop_mode}
              </span>
              <button onClick={() => { setEditJob(job); setShowForm(true); }} className="text-sm text-blue-600 hover:underline">Edit</button>
              <button onClick={() => { if (confirm('Delete this job?')) deleteMutation.mutate(job.id); }} className="text-sm text-red-600 hover:underline">Delete</button>
            </div>
          </div>
        ))}
      </div>

      {showForm && <JobForm job={editJob} onClose={() => setShowForm(false)} />}
    </div>
  );
}
