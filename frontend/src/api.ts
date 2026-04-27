import { Agent, Job, Run, RunContext, Settings } from './types';

const BASE = 'http://localhost:8000';

async function req<T>(method: string, path: string, body?: any): Promise<T> {
  const opts: RequestInit = { method, headers: body ? { 'Content-Type': 'application/json' } : undefined, body: body ? JSON.stringify(body) : undefined };
  const res = await fetch(`${BASE}${path}`, opts);
  if (!res.ok) throw new Error(`${method} ${path} failed: ${res.status}`);
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  agents: {
    list: () => req<Agent[]>('GET', '/api/agents'),
    get: (id: number) => req<Agent>('GET', `/api/agents/${id}`),
    create: (data: Partial<Agent>) => req<Agent>('POST', '/api/agents', data),
    update: (id: number, data: Partial<Agent>) => req<Agent>('PUT', `/api/agents/${id}`, data),
    delete: (id: number) => req<void>('DELETE', `/api/agents/${id}`),
  },
  jobs: {
    list: () => req<Job[]>('GET', '/api/jobs'),
    get: (id: number) => req<Job>('GET', `/api/jobs/${id}`),
    create: (data: Partial<Job>) => req<Job>('POST', '/api/jobs', data),
    update: (id: number, data: Partial<Job>) => req<Job>('PUT', `/api/jobs/${id}`, data),
    delete: (id: number) => req<void>('DELETE', `/api/jobs/${id}`),
  },
  runs: {
    start: (jobId: number, featureRequest: string, context: RunContext) =>
      req<Run>('POST', '/api/runs', { job_id: jobId, feature_request: featureRequest, context }),
    list: (jobId?: number, status?: string) => {
      const params = new URLSearchParams();
      if (jobId) params.set('job_id', String(jobId));
      if (status) params.set('status', status);
      return req<Run[]>('GET', `/api/runs?${params}`);
    },
    get: (id: number) => req<Run>('GET', `/api/runs/${id}`),
    resume: (id: number, response: { response_text: string; uploaded_files: string[] }) =>
      req<any>('POST', `/api/runs/${id}/resume`, response),
    stop: (id: number) => req<any>('POST', `/api/runs/${id}/stop`),
  },
  settings: {
    get: () => req<Settings>('GET', '/api/settings'),
    update: (data: Partial<Settings>) => req<Settings>('PUT', '/api/settings', data),
  },
};
