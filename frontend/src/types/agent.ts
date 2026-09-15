export interface AgentRunRequest {
  task: string;
  agent_type?: string;
  tools?: string[];
  max_steps?: number;
  model?: string;
  temperature?: number;
  system_prompt?: string;
  verbose?: boolean;
  require_approval?: boolean;
}

export interface AgentStep {
  step_number: number;
  action: string;
  thought?: string;
  observation?: string;
  tool_name?: string;
  tool_input?: Record<string, unknown>;
  tool_output?: string;
  elapsed_ms?: number;
  tokens_used?: number;
}

export interface AgentRunResponse {
  run_id: string;
  result: string;
  status: string; // completed | max_steps_reached | error | cancelled
  steps: AgentStep[];
  total_steps: number;
  token_usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
  elapsed_ms: number;
  cost_usd: number;
  loop_detected: boolean;
}

export interface OrchestrateRequest {
  task: string;
  agents: Array<{ name: string; agent_type?: string; tools?: string[] }>;
  workflow?: string;
  max_steps_total?: number;
  model?: string;
}
