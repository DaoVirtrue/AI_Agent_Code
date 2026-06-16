import client from './client';

export interface MCPServer {
  id: string;
  name: string;
  command: string;
  args: string[];
  env: Record<string, string>;
  status: 'connected' | 'disconnected' | 'error';
  tools: string[];
}

export async function listMCPServers(): Promise<MCPServer[]> {
  const response = await client.get<MCPServer[]>('/v1/mcp/servers');
  return response.data;
}
