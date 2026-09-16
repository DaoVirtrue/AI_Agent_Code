import { create } from 'zustand';
import { listMCPServers } from '@/api/mcp';

interface MCPServerItem {
  id: string; name: string; transport: string;
  status: 'connected' | 'disconnected' | 'error';
  toolCount: number;
  command?: string; args?: string; description?: string;
  tools?: string[]; env?: Record<string, string>;
}

interface MCPToolItem {
  name: string;
  server: string;
  description: string;
  inputSchema: Record<string, unknown>;
}

interface MCPState {
  servers: MCPServerItem[];
  serversLoading: boolean;
  tools: MCPToolItem[];
  toolsLoading: boolean;
  testResult: string | null;
  testLoading: boolean;
  error: string | null;

  fetchServers: () => Promise<void>;
  connectServer: (name: string) => Promise<void>;
  disconnectServer: (name: string) => Promise<void>;
  fetchTools: () => Promise<void>;
  testTool: (serverName: string, toolName: string, params: Record<string, unknown>) => Promise<void>;
  clearTestResult: () => void;
  clearError: () => void;
}

export const useMCPStore = create<MCPState>((set, get) => ({
  servers: [],
  serversLoading: false,
  tools: [],
  toolsLoading: false,
  testResult: null,
  testLoading: false,
  error: null,

  fetchServers: async () => {
    set({ serversLoading: true, error: null });
    try {
      const servers = await listMCPServers();
      const mapped: MCPServerItem[] = (Array.isArray(servers) ? servers : []).map((s: any) => ({
        id: s.id || s.name || 'unknown',
        name: s.name || s.id || 'unknown',
        transport: s.transport || 'stdio',
        status: (s.status === 'connected' ? 'connected' : 'disconnected') as any,
        toolCount: (s.tools || []).length,
        tools: s.tools || [],
        description: s.description || '',
      }));
      set({ servers: mapped, serversLoading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch MCP servers';
      set({ error: message, serversLoading: false });
    }
  },

  connectServer: async (name: string) => {
    set({ error: null });
    try {
      await import('@/api/client').then(({ default: client }) =>
        client.post(`/v1/mcp/servers/connect`, { server_name: name })
      );
      set((s) => ({
        servers: s.servers.map((srv) =>
          srv.name === name ? { ...srv, status: 'connected' as const } : srv
        ),
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to connect server';
      set({ error: message });
    }
  },

  disconnectServer: async (name: string) => {
    set({ error: null });
    try {
      await import('@/api/client').then(({ default: client }) =>
        client.post(`/v1/mcp/servers/disconnect`, { server_name: name })
      );
      set((s) => ({
        servers: s.servers.map((srv) =>
          srv.name === name ? { ...srv, status: 'disconnected' as const } : srv
        ),
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to disconnect server';
      set({ error: message });
    }
  },

  fetchTools: async () => {
    set({ toolsLoading: true, error: null });
    try {
      const { default: client } = await import('@/api/client');
      const response = await client.post('/v1/mcp/tools/list');
      const tools: MCPToolItem[] = Array.isArray(response.data) ? response.data : [];
      set({ tools, toolsLoading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch tools';
      set({ error: message, toolsLoading: false });
    }
  },

  testTool: async (serverName, toolName, params) => {
    set({ testLoading: true, testResult: null, error: null });
    try {
      const { default: client } = await import('@/api/client');
      const response = await client.post('/v1/mcp/tools/call', params, {
        params: { server_name: serverName, tool_name: toolName },
      });
      set({ testResult: JSON.stringify(response.data, null, 2), testLoading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Tool test failed';
      set({ error: message, testLoading: false });
    }
  },

  clearTestResult: () => set({ testResult: null }),
  clearError: () => set({ error: null }),
}));
