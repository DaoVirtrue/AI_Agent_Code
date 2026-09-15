import { create } from 'zustand';
import { runEvaluation, listEvalRuns, type EvalResult } from '@/api/eval';

interface EvalState {
  queries: string;
  expectedAnswers: string;
  isRunning: boolean;
  result: EvalResult | null;
  runs: any[];
  error: string | null;
  setQueries: (q: string) => void;
  setExpectedAnswers: (a: string) => void;
  runEval: () => Promise<void>;
  fetchRuns: () => Promise<void>;
}

export const useEvalStore = create<EvalState>((set, get) => ({
  queries: '',
  expectedAnswers: '',
  isRunning: false,
  result: null,
  runs: [],
  error: null,

  setQueries: (q) => set({ queries: q }),
  setExpectedAnswers: (a) => set({ expectedAnswers: a }),

  runEval: async () => {
    const { queries, expectedAnswers } = get();
    if (!queries.trim() || get().isRunning) return;

    set({ isRunning: true, error: null, result: null });

    try {
      const queryList = queries.split('\n').map((s) => s.trim()).filter(Boolean);
      const answerList = expectedAnswers.split('\n').map((s) => s.trim()).filter(Boolean);
      const result = await runEvaluation({
        queries: queryList,
        expected_answers: answerList.length ? answerList : undefined,
      });
      set({ result, isRunning: false });
      // Refresh runs after a successful evaluation
      await get().fetchRuns();
    } catch (err: any) {
      set({ isRunning: false, error: err?.message || '评测失败' });
    }
  },

  fetchRuns: async () => {
    try {
      const { items } = await listEvalRuns(50);
      set({ runs: items });
    } catch {
      // ignore — historical runs are optional
    }
  },
}));
