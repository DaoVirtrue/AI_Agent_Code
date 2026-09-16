import { create } from 'zustand';
import { getSystemStats, getUsageReport } from '@/api/admin';

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
      const [statsData, usageData] = await Promise.all([getSystemStats(), getUsageReport()]);
      const usageSummary = (usageData as any)?.summary || {};
      set({
        stats: {
          totalTokens: usageSummary.total_tokens || 0,
          totalCost: usageSummary.total_cost || 0,
          activeModels: 1,
          healthStatus: (statsData as any)?.status || 'healthy',
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
      const usageData = await getUsageReport({ period: 'monthly' });
      const trendData = (usageData as any)?.trend || [];
      set({ trend: trendData });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Failed to fetch trend data';
      set({ error: message });
    }
  },

  fetchDistribution: async () => {
    set({ error: null });
    try {
      const usageData = await getUsageReport();
      const breakdown = (usageData as any)?.breakdown || [];
      set({
        distribution: (Array.isArray(breakdown) ? breakdown : []).map((b: any) => ({
          model: b.model || 'unknown',
          tokens: b.tokens || 0,
        })),
        costTrend: [],
      });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Failed to fetch distribution data';
      set({ error: message });
    }
  },
}));
