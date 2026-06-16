import { create } from 'zustand';

// ---- Mock admin data ----
const MOCK_TENANTS: Tenant[] = [
  { id: 't_1', name: '默认租户', slug: 'default', tier: 'enterprise', isActive: true, createdAt: '2026-05-01T08:00:00Z', userCount: 128 },
  { id: 't_2', name: '开发团队', slug: 'dev-team', tier: 'pro', isActive: true, createdAt: '2026-05-15T10:30:00Z', userCount: 45 },
  { id: 't_3', name: '测试环境', slug: 'test-env', tier: 'free', isActive: true, createdAt: '2026-06-01T14:00:00Z', userCount: 8 },
];

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

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
      // MOCK: Return pre-built tenants after a short delay
      await sleep(300);
      set({ tenants: [...MOCK_TENANTS], tenantsLoading: false });
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
      await sleep(300);
      const page = (params?.page as number) || 1;
      // MOCK: Generate realistic audit log entries
      const baseTime = Date.now();
      const audits: AuditEntry[] = [];
      const actions = ['登录', '对话', '管理操作', 'API调用', '模型查询', '配置修改', '密钥生成', '用户管理'];
      const users = ['admin', 'developer1', 'developer2', 'api-user'];
      const tenants = ['默认租户', '开发团队', '测试环境'];
      const statuses = ['success', 'success', 'success', 'success', 'failed', 'success', 'success', 'success'];

      for (let i = 0; i < 8; i++) {
        audits.push({
          id: `audit_${page}_${i}`,
          timestamp: new Date(baseTime - i * 3600000).toISOString(),
          tenant: tenants[Math.floor(Math.random() * tenants.length)],
          user: users[Math.floor(Math.random() * users.length)],
          action: actions[Math.floor(Math.random() * actions.length)],
          details: { method: 'POST', ip: '192.168.1.' + (100 + i), user_agent: 'Mozilla/5.0' },
          status: statuses[Math.floor(Math.random() * statuses.length)],
        });
      }
      set({ auditLogs: audits, auditTotal: 45, auditPage: page, auditPageSize: 10, auditLoading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch audit logs';
      set({ error: message, auditLoading: false });
    }
  },

  fetchUsageReport: async () => {
    set({ usageLoading: true, error: null });
    try {
      await sleep(300);
      // MOCK: Generate realistic usage statistics
      const today = new Date();
      const dailyUsage: DailyUsage[] = [];
      for (let i = 6; i >= 0; i--) {
        const d = new Date(today);
        d.setDate(d.getDate() - i);
        dailyUsage.push({
          date: d.toISOString().slice(0, 10),
          calls: 1800 + Math.floor(Math.random() * 500),
          tokens: 300000 + Math.floor(Math.random() * 120000),
        });
      }

      set({
        usageStats: {
          totalCalls: 15200 + Math.floor(Math.random() * 300),
          totalTokens: 2400000 + Math.floor(Math.random() * 200000),
          totalCost: 8.15 + Math.random() * 1.5,
        },
        dailyUsage,
        modelBreakdown: [
          { model: 'deepseek-chat', calls: 12400, tokens: 1950000, cost: 6.8 },
          { model: 'deepseek-reasoner', calls: 2600, tokens: 420000, cost: 1.35 },
        ],
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
