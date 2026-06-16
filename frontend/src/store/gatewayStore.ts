import { create } from 'zustand';
import type { ModelInfo } from '@/types';

interface ProviderState {
  name: string;
  status: 'healthy' | 'degraded' | 'unhealthy' | 'unknown';
  latencyP50: number;
  latencyP99: number;
  uptime: number;
  circuitState: 'CLOSED' | 'OPEN' | 'HALF_OPEN';
  failureCount: number;
  lastTransitionTime: string;
  modelCount: number;
}

interface RateLimitTier {
  id: string;
  name: string;
  rpmLimit: number;
  dailyTokenLimit: number;
}

interface GatewayState {
  models: ModelInfo[];
  providers: ProviderState[];
  rateLimitTiers: RateLimitTier[];
  gatewayStatus: string | null;
  isLoading: boolean;
  error: string | null;

  fetchModels: () => Promise<void>;
  fetchProviders: () => Promise<void>;
  fetchRateLimitTiers: () => Promise<void>;
  updateRateLimitTier: (id: string, data: { rpmLimit?: number; dailyTokenLimit?: number }) => Promise<void>;
  refreshGatewayHealth: () => Promise<void>;
}

export const useGatewayStore = create<GatewayState>((set, get) => ({
  models: [],
  providers: [],
  rateLimitTiers: [],
  gatewayStatus: null,
  isLoading: false,
  error: null,

  fetchModels: async () => {
    set({ isLoading: true, error: null });
    try {
      // MOCK: Return DeepSeek models with real pricing
      const models: ModelInfo[] = [
        {
          id: 'deepseek-chat',
          name: 'DeepSeek Chat',
          provider: 'DeepSeek',
          max_tokens: 131072,
          supports_streaming: true,
          supports_tools: true,
          cost_per_1k_input: 0.00027,
          cost_per_1k_output: 0.0011,
        },
        {
          id: 'deepseek-reasoner',
          name: 'DeepSeek Reasoner',
          provider: 'DeepSeek',
          max_tokens: 65536,
          supports_streaming: true,
          supports_tools: false,
          cost_per_1k_input: 0.00055,
          cost_per_1k_output: 0.00219,
        },
      ];
      set({ models, isLoading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch models';
      set({ error: message, isLoading: false });
    }
  },

  fetchProviders: async () => {
    set({ error: null });
    try {
      // MOCK: Show only DeepSeek as the configured provider
      const providers: ProviderState[] = [
        {
          name: 'DeepSeek',
          status: 'healthy',
          latencyP50: 185,
          latencyP99: 320,
          uptime: 99.9,
          circuitState: 'CLOSED',
          failureCount: 0,
          lastTransitionTime: new Date().toISOString(),
          modelCount: 2,
        },
      ];
      set({ providers });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch providers';
      set({ error: message });
    }
  },

  fetchRateLimitTiers: async () => {
    try {
      const tiers: RateLimitTier[] = [
        { id: '1', name: 'Free', rpmLimit: 10, dailyTokenLimit: 100000 },
        { id: '2', name: 'Pro', rpmLimit: 100, dailyTokenLimit: 1000000 },
        { id: '3', name: 'Enterprise', rpmLimit: 1000, dailyTokenLimit: 10000000 },
      ];
      set({ rateLimitTiers: tiers });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch rate limit tiers';
      set({ error: message });
    }
  },

  updateRateLimitTier: async (id: string, data) => {
    try {
      set((state) => ({
        rateLimitTiers: state.rateLimitTiers.map((t) =>
          t.id === id ? { ...t, ...data } : t
        ),
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update rate limit';
      set({ error: message });
    }
  },

  refreshGatewayHealth: async () => {
    try {
      // MOCK: DeepSeek is always healthy in demo mode
      set({ gatewayStatus: 'healthy' });
    } catch {
      set({ gatewayStatus: 'unhealthy' });
    }
  },
}));
