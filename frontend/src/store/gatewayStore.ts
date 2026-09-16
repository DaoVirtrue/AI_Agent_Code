import { create } from 'zustand';
import type { ModelInfo } from '@/types';
import { listModels, getProviderHealth } from '@/api/gateway';

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
      const models = await listModels();
      set({ models, isLoading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch models';
      set({ error: message, isLoading: false });
    }
  },

  fetchProviders: async () => {
    set({ error: null });
    try {
      const health = await getProviderHealth();
      const providers: ProviderState[] = (Array.isArray(health) ? health : []).map((h: any, i: number) => ({
        name: h.provider || `provider-${i}`,
        status: (h.status as any) || 'unknown',
        latencyP50: h.latency || 0,
        latencyP99: h.latency || 0,
        uptime: 99.9,
        circuitState: 'CLOSED',
        failureCount: 0,
        lastTransitionTime: new Date().toISOString(),
        modelCount: 0,
      }));
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
