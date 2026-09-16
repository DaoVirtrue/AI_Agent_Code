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

export interface MCPToolDef {
  name: string;
  description: string;
  inputSchema?: Record<string, unknown>;
  server_name: string;
}

export async function listMCPServers(): Promise<any[]> {
  const response = await client.get<any[]>('/v1/mcp/servers');
  return response.data;
}

export async function listMCPTools(serverName?: string): Promise<{ tools: MCPToolDef[]; servers: string[] }> {
  const response = await client.post('/v1/mcp/tools/list', {}, { params: serverName ? { server_name: serverName } : {} });
  return response.data;
}

export async function connectMCPServer(payload: { name: string; url: string; transport?: string }): Promise<any> {
  const response = await client.post('/v1/mcp/servers/connect', null, { params: payload });
  return response.data;
}

export async function disconnectMCPServer(name: string): Promise<any> {
  const response = await client.delete(`/v1/mcp/servers/${name}`);
  return response.data;
}

export async function callMCPTool(serverName: string, toolName: string, arguments_: Record<string, unknown>): Promise<any> {
  const response = await client.post('/v1/mcp/tools/call', arguments_, {
    params: { server_name: serverName, tool_name: toolName },
  });
  return response.data;
}
