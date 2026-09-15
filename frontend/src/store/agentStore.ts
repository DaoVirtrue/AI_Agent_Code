import { create } from 'zustand';
import type { AgentStep } from '@/types';
import { runAgent as runAgentApi } from '@/api/agent';

interface AgentState {
  agentType: string;
  task: string;
  model: string;
  maxSteps: number;
  tools: string[];
  isRunning: boolean;
  runId: string | null;
  steps: AgentStep[];
  finalResult: string | null;
  finalStatus: string | null;
  totalSteps: number;
  elapsedMs: number;
  tokenUsage: { prompt_tokens: number; completion_tokens: number; total_tokens: number } | null;
  costUsd: number;
  loopDetected: boolean;
  error: string | null;
  setAgentType: (t: string) => void;
  setTask: (t: string) => void;
  setModel: (m: string) => void;
  setMaxSteps: (n: number) => void;
  setTools: (t: string[]) => void;
  runAgent: () => Promise<void>;
  stopAgent: () => void;
  clearResult: () => void;
}

export const useAgentStore = create<AgentState>((set, get) => ({
  agentType: 'react',
  task: '',
  model: 'deepseek-chat',
  maxSteps: 15,
  tools: [],
  isRunning: false,
  runId: null,
  steps: [],
  finalResult: null,
  finalStatus: null,
  totalSteps: 0,
  elapsedMs: 0,
  tokenUsage: null,
  costUsd: 0,
  loopDetected: false,
  error: null,

  setAgentType: (t) => set({ agentType: t }),
  setTask: (t) => set({ task: t }),
  setModel: (m) => set({ model: m }),
  setMaxSteps: (n) => set({ maxSteps: n }),
  setTools: (t) => set({ tools: t }),

  runAgent: async () => {
    const s = get();
    if (s.isRunning || !s.task.trim()) return;

    set({
      isRunning: true, steps: [], finalResult: null, finalStatus: null,
      error: null, runId: null, elapsedMs: 0, tokenUsage: null,
      costUsd: 0, totalSteps: 0, loopDetected: false,
    });

    try {
      const response = await runAgentApi({
        task: s.task,
        agent_type: s.agentType,
        model: s.model,
        max_steps: s.maxSteps,
        tools: s.tools.length ? s.tools : undefined,
      });

      set({
        steps: response.steps,
        finalResult: response.result,
        finalStatus: response.status,
        runId: response.run_id,
        totalSteps: response.total_steps,
        elapsedMs: response.elapsed_ms,
        tokenUsage: response.token_usage,
        costUsd: response.cost_usd,
        loopDetected: response.loop_detected,
        isRunning: false,
      });
    } catch (err: any) {
      set({
        isRunning: false,
        error: err?.message || 'Agent 执行失败',
        finalStatus: 'error',
      });
    }
  },

  stopAgent: () => set({ isRunning: false }),
  clearResult: () => set({
    steps: [], finalResult: null, finalStatus: null, runId: null,
    totalSteps: 0, elapsedMs: 0, tokenUsage: null, costUsd: 0,
    loopDetected: false, error: null,
  }),
}));
