import client from './client';
import { AgentRunRequest, AgentRunResponse } from '@/types';

export async function runAgent(request: AgentRunRequest): Promise<AgentRunResponse> {
  const response = await client.post<AgentRunResponse>('/v1/agent/run', request);
  return response.data;
}
