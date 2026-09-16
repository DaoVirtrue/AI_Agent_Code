import { create } from 'zustand';
import { listTenants, getAuditLogs, getSystemStats, getUsageReport } from '@/api/admin';

interface Tenant {
  id: string;
  name: string;
  slug: string;
  tier: string;
  isActive: boolean;
  createdAt: string;
  userCount?: number;
}

interface AuditEntry {
  id: string;
  timestamp: string;
  tenant: string;
  user: string;
  action: string;
  details: Record<string, unknown>;
  status: string;
}

interface ApiKey {
  id: string;
  name: string;
  keyPrefix: string;
  scopes: string[];
  rateLimit: number;
  expiresAt: string;
  lastUsedAt: string;
  isActive: boolean;
}

interface UsageStats {
  totalCalls: number;
  totalTokens: number;
  totalCost: number;
}

interface DailyUsage {
  date: string;
  calls: number;
  tokens: number;
}

interface ModelBreakdown {
  model: string;
  calls: number;
  tokens: number;
  cost: number;
}

interface AdminState {
  tenants: Tenant[];
  tenantsLoading: boolean;
  auditLogs: AuditEntry[];
  auditLoading: boolean;
  auditTotal: number;
  auditPage: number;
  auditPageSize: number;
  apiKeys: ApiKey[];
  apiKeysLoading: boolean;
  usageStats: UsageStats | null;
  dailyUsage: DailyUsage[];
  modelBreakdown: ModelBreakdown[];
  usageLoading: boolean;
  systemHealth: Record<string, unknown> | null;
  error: string | null;
  newKeyPlain: string | null;

  fetchTenants: () => Promise<void>;
  createTenant: (data: Partial<Tenant>) => Promise<void>;
  updateTenant: (id: string, data: Partial<Tenant>) => Promise<void>;
  deleteTenant: (id: string) => Promise<void>;
  fetchAuditLogs: (params?: Record<string, unknown>) => Promise<void>;
  fetchUsageReport: (period: string) => Promise<void>;
  fetchApiKeys: () => Promise<void>;
  generateApiKey: (name: string) => Promise<void>;
  revokeApiKeyAction: (keyId: string) => Promise<void>;
  enableApiKeyAction: (keyId: string) => Promise<void>;
  deleteApiKeyAction: (keyId: string) => Promise<void>;
  clearNewKey: () => void;
  clearError: () => void;
}

export const useAdminStore = create<AdminState>((set, get) => ({
  tenants: [],
  tenantsLoading: false,
  auditLogs: [],
  auditLoading: false,
  auditTotal: 0,
  auditPage: 1,
  auditPageSize: 10,
  apiKeys: [],
  apiKeysLoading: false,
  usageStats: null,
  dailyUsage: [],
  modelBreakdown: [],
  usageLoading: false,
  systemHealth: null,
  error: null,
  newKeyPlain: null,

  fetchTenants: async () => {
    set({ tenantsLoading: true, error: null });
    try {
      const data = await listTenants();
      const tenants: Tenant[] = (Array.isArray(data) ? data : (data as any)?.items || []).map((t: any) => ({
        id: t.id || 'unknown',
        name: t.name || 'unknown',
        slug: t.slug || '',
        tier: t.tier || 'free',
        isActive: t.is_active ?? true,
        createdAt: t.created_at || new Date().toISOString(),
        userCount: t.user_count || 0,
      }));
      set({ tenants, tenantsLoading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch tenants';
      set({ error: message, tenantsLoading: false });
    }
  },

  createTenant: async (data) => {
    set({ error: null });
    try {
      const newTenant: Tenant = {
        id: `tenant_${Date.now()}`,
        name: data.name || 'New Tenant',
        slug: data.slug || data.name?.toLowerCase().replace(/\s+/g, '-') || 'new-tenant',
        tier: data.tier || 'free',
        isActive: data.isActive ?? true,
        createdAt: new Date().toISOString(),
      };
      set((s) => ({ tenants: [newTenant, ...s.tenants] }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create tenant';
      set({ error: message });
    }
  },

  updateTenant: async (id, data) => {
    set({ error: null });
    try {
      set((s) => ({
        tenants: s.tenants.map((t) => (t.id === id ? { ...t, ...data } : t)),
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update tenant';
      set({ error: message });
    }
  },

  deleteTenant: async (id) => {
    try {
      set((s) => ({ tenants: s.tenants.filter((t) => t.id !== id) }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete tenant';
      set({ error: message });
    }
  },

  fetchAuditLogs: async (params) => {
    set({ auditLoading: true, error: null });
    try {
      const page = (params?.page as number) || 1;
      const data = await getAuditLogs({ page, pageSize: params?.pageSize as number || 10 });
      const items = (data as any)?.items || (Array.isArray(data) ? data : []);
      const audits: AuditEntry[] = items.map((a: any, i: number) => ({
        id: a.id || `audit_${page}_${i}`,
        timestamp: a.timestamp || a.created_at || new Date().toISOString(),
        tenant: a.tenant || a.tenant_id || '-',
        user: a.user || a.user_id || '-',
        action: a.action || a.operation || '-',
        details: a.details || {},
        status: a.status || 'success',
      }));
      set({
        auditLogs: audits,
        auditTotal: (data as any)?.total || audits.length,
        auditPage: page,
        auditPageSize: (params?.pageSize as number) || 10,
        auditLoading: false,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch audit logs';
      set({ error: message, auditLoading: false });
    }
  },

  fetchUsageReport: async () => {
    set({ usageLoading: true, error: null });
    try {
      const data = await getUsageReport();
      const summary = (data as any)?.summary || {};
      const breakdown = (data as any)?.breakdown || [];
      set({
        usageStats: {
          totalCalls: summary.total_calls || summary.calls || 0,
          totalTokens: summary.total_tokens || summary.tokens || 0,
          totalCost: summary.total_cost || summary.cost || 0,
        },
        dailyUsage: [],
        modelBreakdown: (Array.isArray(breakdown) ? breakdown : []).map((b: any) => ({
          model: b.model || 'unknown',
          calls: b.calls || 0,
          tokens: b.tokens || 0,
          cost: b.cost || 0,
        })),
        usageLoading: false,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch usage report';
      set({ error: message, usageLoading: false });
    }
  },

  fetchApiKeys: async () => {
    set({ apiKeysLoading: true, error: null });
    try {
      // MOCK: Show DeepSeek key and production environment key
      const keys: ApiKey[] = [
        {
          id: 'k_ds',
          name: 'DeepSeek API Key',
          keyPrefix: 'sk-ds-****',
          scopes: ['read', 'write'],
          rateLimit: 100,
          expiresAt: 'never',
          lastUsedAt: new Date().toISOString(),
          isActive: true,
        },
        {
          id: 'k_prod',
          name: '生产环境 Key',
          keyPrefix: 'sk-prod-****',
          scopes: ['read'],
          rateLimit: 500,
          expiresAt: new Date(Date.now() + 31536000000).toISOString(),
          lastUsedAt: new Date(Date.now() - 86400000).toISOString(),
          isActive: true,
        },
      ];
      set({ apiKeys: keys, apiKeysLoading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch API keys';
      set({ error: message, apiKeysLoading: false });
    }
  },

  generateApiKey: async (name) => {
    set({ error: null });
    try {
      const newKey: ApiKey = {
        id: `k_${Date.now()}`,
        name,
        keyPrefix: 'sk-f9a0****',
        scopes: ['read', 'write'],
        rateLimit: 50,
        expiresAt: new Date(Date.now() + 31536000000).toISOString(),
        lastUsedAt: '-',
        isActive: true,
      };
      const rawKey = 'sk-f9a0' + Math.random().toString(36).substring(2, 10) + Math.random().toString(36).substring(2, 10);
      set((s) => ({
        apiKeys: [newKey, ...s.apiKeys],
        newKeyPlain: rawKey,
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to generate API key';
      set({ error: message });
    }
  },

  revokeApiKeyAction: async (keyId) => {
    try {
      set((s) => ({
        apiKeys: s.apiKeys.map((k) => (k.id === keyId ? { ...k, isActive: false } : k)),
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to revoke API key';
      set({ error: message });
    }
  },

  enableApiKeyAction: async (keyId) => {
    set((s) => ({
      apiKeys: s.apiKeys.map((k) => (k.id === keyId ? { ...k, isActive: true } : k)),
    }));
  },

  deleteApiKeyAction: async (keyId) => {
    set((s) => ({
      apiKeys: s.apiKeys.filter((k) => k.id !== keyId),
    }));
  },

  clearNewKey: () => set({ newKeyPlain: null }),
  clearError: () => set({ error: null }),
}));
