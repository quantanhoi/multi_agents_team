export type AgentRole = 'planner' | 'coder' | 'tester';
export type RunStatus = 'pending' | 'planning_draft' | 'planning_review_coder' | 'planning_review_tester' | 'planning_finalize' | 'coding' | 'testing' | 'evaluating' | 'waiting_for_human' | 'done' | 'failed';

export interface Agent {
  id: number; name: string; role: AgentRole; model_name: string;
  system_prompt: string; temperature: number; ollama_endpoint: string;
  created_at: string; updated_at: string;
}

export interface AgentOverride {
  model_name?: string | null; temperature?: number | null; system_prompt_append?: string | null;
}

export interface Job {
  id: number; name: string; description: string;
  planner_agent_id: number; coder_agent_id: number; tester_agent_id: number;
  agent_overrides: { planner?: AgentOverride; coder?: AgentOverride; tester?: AgentOverride };
  loop_mode: 'automatic' | 'manual'; max_iterations: number;
  created_at: string; updated_at: string;
}

export interface RunContext {
  selected_files: string[]; known_bugs: string[]; constraints: string[]; extra_notes: string;
}

export interface Run {
  id: number; job_id: number; status: RunStatus; feature_request: string;
  context: RunContext; iterations: number; roadmap: any;
  coder_outputs: any[]; test_reports: any[]; human_requests: any[];
  started_at: string; completed_at: string | null;
}

export interface Settings {
  working_dir: string; ollama_endpoint: string; default_temperature: number;
}

export interface HumanInputRequest {
  message: string; input_type: 'text' | 'file_upload' | 'screenshot_upload'; requested_by: string;
}

export interface WSMessage {
  type: 'phase_change' | 'agent_output' | 'human_input_required' | 'done' | 'failed' | 'error';
  phase?: string; message?: string; agent?: string; output?: any;
  requested_by?: string; input_type?: string; status?: string; summary?: string;
  retryable?: boolean;
}
