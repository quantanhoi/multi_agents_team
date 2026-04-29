import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { api } from './api';

describe('api client', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function mockResponse(body: unknown, status = 200) {
    return Promise.resolve({
      ok: status >= 200 && status < 300,
      status,
      json: () => Promise.resolve(body),
    } as Response);
  }

  it('lists agents', async () => {
    const agents = [{ id: 1, name: 'Planner', role: 'planner', model_name: 'gpt-4', system_prompt: '', temperature: 0.3, ollama_endpoint: '', api_key: '', created_at: '', updated_at: '' }];
    (globalThis.fetch as any).mockReturnValue(mockResponse(agents));
    const result = await api.agents.list();
    expect(result).toEqual(agents);
    expect(globalThis.fetch).toHaveBeenCalledWith(expect.stringContaining('/api/agents'), expect.any(Object));
  });

  it('creates an agent', async () => {
    const agent = { id: 1, name: 'Coder', role: 'coder', model_name: 'glm-5.1', system_prompt: 'test', temperature: 0.5, ollama_endpoint: '', api_key: '', created_at: '', updated_at: '' };
    (globalThis.fetch as any).mockReturnValue(mockResponse(agent));
    const result = await api.agents.create({ name: 'Coder', model_name: 'glm-5.1' });
    expect(result).toEqual(agent);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/agents'),
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ name: 'Coder', model_name: 'glm-5.1' }) })
    );
  });

  it('deletes an agent', async () => {
    (globalThis.fetch as any).mockReturnValue(mockResponse(undefined, 204));
    await api.agents.delete(1);
    expect(globalThis.fetch).toHaveBeenCalledWith(expect.stringContaining('/api/agents/1'), expect.objectContaining({ method: 'DELETE' }));
  });

  it('throws on HTTP error', async () => {
    (globalThis.fetch as any).mockReturnValue(mockResponse({ detail: 'Not found' }, 404));
    await expect(api.agents.get(99)).rejects.toThrow('GET /api/agents/99 failed: 404');
  });

  it('lists jobs', async () => {
    const jobs = [{ id: 1, name: 'Default', description: '', planner_agent_id: 1, coder_agent_id: 2, tester_agent_id: 3, agent_overrides: {}, loop_mode: 'automatic', max_iterations: 5, created_at: '', updated_at: '' }];
    (globalThis.fetch as any).mockReturnValue(mockResponse(jobs));
    const result = await api.jobs.list();
    expect(result).toEqual(jobs);
  });

  it('starts a run', async () => {
    const run = { id: 1, job_id: 1, status: 'pending', feature_request: 'test', context: { selected_files: [], known_bugs: [], constraints: [], extra_notes: '' }, iterations: 0, roadmap: null, coder_outputs: [], test_reports: [], human_requests: [], started_at: '', completed_at: null };
    (globalThis.fetch as any).mockReturnValue(mockResponse(run));
    const result = await api.runs.start(1, 'test', { selected_files: [], known_bugs: [], constraints: [], extra_notes: '' });
    expect(result).toEqual(run);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/runs'),
      expect.objectContaining({ method: 'POST', body: expect.stringContaining('test') })
    );
  });

  it('fetches settings', async () => {
    const settings = { working_dir: '/tmp', ollama_endpoint: 'http://localhost:11435', ollama_api_key: '', default_temperature: 0.3 };
    (globalThis.fetch as any).mockReturnValue(mockResponse(settings));
    const result = await api.settings.get();
    expect(result).toEqual(settings);
  });
});
