import { create } from 'zustand';
import type { AgentStep } from '@/types';

interface AgentState {
  agentType: string; task: string; model: string; maxSteps: number; tools: string[];
  isRunning: boolean; runId: string | null; steps: AgentStep[];
  finalResult: string | null; finalStatus: string | null; totalSteps: number;
  elapsedMs: number; tokenUsage: { prompt_tokens: number; completion_tokens: number; total_tokens: number } | null;
  costUsd: number; error: string | null;
  setAgentType: (t: string) => void; setTask: (t: string) => void; setModel: (m: string) => void;
  setMaxSteps: (n: number) => void; setTools: (t: string[]) => void;
  runAgent: () => Promise<void>; stopAgent: () => void; clearResult: () => void;
}

export const useAgentStore = create<AgentState>((set, get) => ({
  agentType: 'react', task: '', model: 'deepseek-chat', maxSteps: 15, tools: [],
  isRunning: false, runId: null, steps: [], finalResult: null, finalStatus: null,
  totalSteps: 0, elapsedMs: 0, tokenUsage: null, costUsd: 0, error: null,

  setAgentType: (t) => set({ agentType: t }),
  setTask: (t) => set({ task: t }),
  setModel: (m) => set({ model: m }),
  setMaxSteps: (n) => set({ maxSteps: n }),
  setTools: (t) => set({ tools: t }),

  runAgent: async () => {
    const s = get();
    if (s.isRunning || !s.task.trim()) return;

    set({ isRunning: true, steps: [], finalResult: null, finalStatus: null, error: null, runId: `run_${Date.now()}`, elapsedMs: 0, tokenUsage: null, costUsd: 0, totalSteps: 0 });

    const startTime = Date.now();
    try {
      const response = await fetch('/api/v1/chat/completions', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: s.model || 'deepseek-chat', max_tokens: 2048,
          messages: [
            { role: 'system', content: '你是AI Agent。请逐步分析任务：## 思考\n(分析)\n## 行动\n(步骤)\n## 最终答案\n(结论)' },
            { role: 'user', content: s.task },
          ],
        }),
      });
      if (!response.ok) throw new Error(`API ${response.status}`);
      const data = await response.json();
      const reply = data.choices?.[0]?.message?.content || '(无回复)';
      const usage = data.usage || {};
      const elapsed = Date.now() - startTime;

      // Create steps from response sections
      const steps: AgentStep[] = [];
      const sections = reply.split(/\n##\s+/);
      let stepNum = 0;
      for (const section of sections) {
        const trimmed = section.trim();
        if (!trimmed) continue;
        let type = 'thought'; let content = trimmed;
        if (trimmed.startsWith('思考')) { type = 'thought'; content = trimmed.replace('思考', '').trim(); }
        else if (trimmed.startsWith('行动')) { type = 'action'; content = trimmed.replace('行动', '').trim(); }
        else if (trimmed.startsWith('最终答案')) { type = 'observation'; content = trimmed.replace('最终答案', '').trim(); }
        steps.push({ step_number: ++stepNum, type, content, thought: type === 'thought' ? content : '', action: type === 'action' ? content : '', observation: type === 'observation' ? content : '', tool_name: '', tool_input: '', tool_output: '', elapsed_ms: 0, tokens_used: 0 });
      }
      if (steps.length === 0) {
        steps.push({ step_number: 1, type: 'observation', content: reply, thought: '', action: '', observation: reply, tool_name: '', tool_input: '', tool_output: '', elapsed_ms: 0, tokens_used: 0 });
      }

      const promptTokens = usage.prompt_tokens || 0;
      const completionTokens = usage.completion_tokens || 0;
      const cost = (promptTokens * 0.27 + completionTokens * 1.10) / 1000000; // DeepSeek pricing

      set({ steps, finalResult: reply, finalStatus: 'completed', isRunning: false, tokenUsage: { prompt_tokens: promptTokens, completion_tokens: completionTokens, total_tokens: promptTokens + completionTokens }, costUsd: Math.round(cost * 10000) / 10000, elapsedMs: elapsed, totalSteps: steps.length });
    } catch (err: any) {
      if (err.name === 'AbortError') { set({ isRunning: false, finalStatus: 'cancelled' }); return; }
      set({ isRunning: false, error: err?.message || 'Agent执行失败', finalStatus: 'error' });
    }
  },

  stopAgent: () => { set({ isRunning: false }); },
  clearResult: () => set({ steps: [], finalResult: null, finalStatus: null, runId: null, totalSteps: 0, elapsedMs: 0, tokenUsage: null, costUsd: 0, error: null }),
}));
