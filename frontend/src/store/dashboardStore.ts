import { create } from 'zustand';

interface DashboardStats {
  totalTokens: number;
  totalCost: number;
  activeModels: number;
  healthStatus: string;
}

interface TrendItem {
  date: string;
  input: number;
  output: number;
}

interface DistributionItem {
  model: string;
  tokens: number;
}

interface CostTrendItem {
  date: string;
  cost: number;
}

interface DashboardState {
  stats: DashboardStats | null;
  trend: TrendItem[] | null;
  distribution: DistributionItem[] | null;
  costTrend: CostTrendItem[] | null;
  isLoading: boolean;
  error: string | null;

  fetchStats: () => Promise<void>;
  fetchTrend: () => Promise<void>;
  fetchDistribution: () => Promise<void>;
}

function generateMonthlyTrend(months: number): TrendItem[] {
  const data: TrendItem[] = [];
  const now = new Date();
  for (let i = months - 1; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const dateStr = d.toISOString().slice(0, 7);
    const baseInput = 500000 + Math.random() * 1500000;
    const baseOutput = 200000 + Math.random() * 600000;
    data.push({
      date: dateStr,
      input: Math.round(baseInput),
      output: Math.round(baseOutput),
    });
  }
  return data;
}

function generateCostTrend(months: number): CostTrendItem[] {
  const data: CostTrendItem[] = [];
  const now = new Date();
  for (let i = months - 1; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const dateStr = d.toISOString().slice(0, 7);
    data.push({
      date: dateStr,
      cost: Math.round((10 + Math.random() * 90) * 100) / 100,
    });
  }
  return data;
}

function generateDistribution(): DistributionItem[] {
  return [
    { model: 'deepseek-v3', tokens: Math.round(1800000 + Math.random() * 400000) },
  ];
}

export const useDashboardStore = create<DashboardState>((set) => ({
  stats: null,
  trend: null,
  distribution: null,
  costTrend: null,
  isLoading: false,
  error: null,

  fetchStats: async () => {
    set({ isLoading: true, error: null });
    try {
      // MOCK: Simulate network delay then return realistic stats
      await new Promise((resolve) => setTimeout(resolve, 400));

      set({
        stats: {
          totalTokens: 2450000 + Math.floor(Math.random() * 200000),
          totalCost: Math.round((12.35 + Math.random() * 2) * 100) / 100,
          activeModels: 1,
          healthStatus: 'healthy',
        },
        isLoading: false,
      });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Failed to fetch dashboard stats';
      set({ error: message, isLoading: false });
    }
  },

  fetchTrend: async () => {
    set({ error: null });
    try {
      await new Promise((resolve) => setTimeout(resolve, 300));
      set({ trend: generateMonthlyTrend(6) });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Failed to fetch trend data';
      set({ error: message });
    }
  },

  fetchDistribution: async () => {
    set({ error: null });
    try {
      await new Promise((resolve) => setTimeout(resolve, 300));
      set({
        distribution: generateDistribution(),
        costTrend: generateCostTrend(6),
      });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Failed to fetch distribution data';
      set({ error: message });
    }
  },
}));
