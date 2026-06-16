import { create } from 'zustand';

// ---- Mock MCP data ----
const MOCK_SERVERS: MCPServerItem[] = [
  {
    id: 'mcp_1', name: '文件系统工具', transport: 'stdio', status: 'connected', toolCount: 4,
    command: 'npx', args: ['-y', '@modelcontextprotocol/server-filesystem', '/tmp'],
    tools: ['read_file', 'write_file', 'list_directory', 'search_files'],
    env: { HOME: '/root' },
    description: '读写本地文件、创建目录、搜索文件内容',
  },
  {
    id: 'mcp_2', name: '网络搜索 (Brave)', transport: 'http', status: 'disconnected', toolCount: 2,
    command: 'npx', args: ['-y', '@modelcontextprotocol/server-brave-search'],
    tools: ['web_search', 'local_search'],
    env: { BRAVE_API_KEY: 'your-key' },
    description: '通过 Brave Search API 搜索网页内容',
  },
  {
    id: 'mcp_3', name: '数据库查询 (PostgreSQL)', transport: 'stdio', status: 'disconnected', toolCount: 3,
    command: 'npx', args: ['-y', '@modelcontextprotocol/server-postgres', 'postgresql://localhost/db'],
    tools: ['execute_sql', 'list_tables', 'describe_table'],
    env: { PGHOST: 'localhost', PGPORT: '5432' },
    description: '执行 SQL 查询、查看表结构、导出数据',
  },
  {
    id: 'mcp_4', name: 'GitHub 代码仓库', transport: 'http', status: 'disconnected', toolCount: 5,
    command: 'npx', args: ['-y', '@modelcontextprotocol/server-github'],
    tools: ['read_repo', 'create_issue', 'list_prs', 'search_code', 'get_file'],
    env: { GITHUB_TOKEN: 'ghp_xxx' },
    description: '读取代码、管理 Issue、提交 PR',
  },
  {
    id: 'mcp_5', name: 'REST API 网关', transport: 'http', status: 'disconnected', toolCount: 4,
    command: 'npx', args: ['-y', '@anthropic/mcp-server-rest-api'],
    tools: ['get', 'post', 'put', 'delete'],
    env: { BASE_URL: 'https://api.example.com' },
    description: '调用任意 HTTP API',
  },
];

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
  servers: [...MOCK_SERVERS],
  serversLoading: false,
  tools: [],
  toolsLoading: false,
  testResult: null,
  testLoading: false,
  error: null,

  fetchServers: async () => {
    set({ serversLoading: true, error: null });
    try {
      // MOCK: Return pre-built MCP servers after a short delay
      await new Promise((r) => setTimeout(r, 300));
      set({ servers: [...MOCK_SERVERS], serversLoading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch MCP servers';
      set({ error: message, serversLoading: false });
    }
  },

  connectServer: async (name: string) => {
    set({ error: null });
    try {
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
      const tools: MCPToolItem[] = [];
      set({ tools, toolsLoading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch tools';
      set({ error: message, toolsLoading: false });
    }
  },

  testTool: async (serverName, toolName, params) => {
    set({ testLoading: true, testResult: null, error: null });
    try {
      await new Promise((r) => setTimeout(r, 800));
      set({
        testResult: JSON.stringify(
          { status: 'success', tool: toolName, server: serverName, params, result: { message: 'Tool executed successfully', data: { output: `Result for ${toolName}` } } },
          null,
          2
        ),
        testLoading: false,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Tool test failed';
      set({ error: message, testLoading: false });
    }
  },

  clearTestResult: () => set({ testResult: null }),
  clearError: () => set({ error: null }),
}));
