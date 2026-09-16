import { create } from 'zustand';
import { listMCPServers, listMCPTools, connectMCPServer, disconnectMCPServer, callMCPTool, type MCPToolDef } from '@/api/mcp';

interface MCPServerItem {
  id: string; name: string; transport: string;
  status: 'connected' | 'disconnected' | 'error';
  toolCount: number;
  url?: string; description?: string;
  tools?: any[]; env?: Record<string, string>;
}

interface MCPState {
  servers: MCPServerItem[];
  serversLoading: boolean;
  tools: MCPToolDef[];
  toolsLoading: boolean;
  testResult: string | null;
  testLoading: boolean;
  error: string | null;

  fetchServers: () => Promise<void>;
  fetchTools: (serverName?: string) => Promise<void>;
  connectServer: (name: string, url?: string) => Promise<void>;
  disconnectServer: (name: string) => Promise<void>;
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
        id: s.name || 'unknown',
        name: s.name || 'unknown',
        transport: s.transport || 'stdio',
        status: (s.status === 'connected' ? 'connected' : 'disconnected') as any,
        toolCount: s.tools_count ?? (s.tools || []).length,
        tools: s.tools || [],
        url: s.url || '',
        description: s.description || '',
      }));
      set({ servers: mapped, serversLoading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch MCP servers';
      set({ error: message, serversLoading: false });
    }
  },

  fetchTools: async (serverName?: string) => {
    set({ toolsLoading: true, error: null });
    try {
      const { tools } = await listMCPTools(serverName);
      set({ tools: tools || [], toolsLoading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch tools';
      set({ error: message, toolsLoading: false });
    }
  },

  connectServer: async (name: string, url?: string) => {
    set({ error: null });
    try {
      await connectMCPServer({ name, url: url || '', transport: 'builtin' });
      await get().fetchServers();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to connect server';
      set({ error: message });
    }
  },

  disconnectServer: async (name: string) => {
    set({ error: null });
    try {
      await disconnectMCPServer(name);
      await get().fetchServers();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to disconnect server';
      set({ error: message });
    }
  },

  testTool: async (serverName, toolName, params) => {
    set({ testLoading: true, testResult: null, error: null });
    try {
      const response = await callMCPTool(serverName, toolName, params);
      set({ testResult: JSON.stringify(response, null, 2), testLoading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Tool test failed';
      set({ error: message, testLoading: false });
    }
  },

  clearTestResult: () => set({ testResult: null }),
  clearError: () => set({ error: null }),
}));
