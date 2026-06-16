export interface AgentRunRequest {
  agent_type: string;
  input: string;
  model?: string;
  parameters?: Record<string, unknown>;
  tenant_id?: string;
}

export interface AgentRunResponse {
  run_id: string;
  status: 'completed' | 'failed' | 'running';
  output: string;
  steps: AgentStep[];
  token_usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
  execution_time_ms: number;
}

export interface AgentStep {
  step_number: number;
  type: 'thought' | 'action' | 'observation' | 'final';
  content: string;
  tool_name?: string;
  tool_input?: Record<string, unknown>;
  token_usage?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
  timestamp: string;
}

export interface OrchestrateRequest {
  task: string;
  agents: string[];
  model?: string;
  tenant_id?: string;
}
