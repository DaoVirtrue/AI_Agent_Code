import client from './client';

export interface ExpertDefineRequest {
  name: string;
  role?: string;
  system_prompt?: string;
  skills?: string[];
  knowledge_bases?: string[];
  description?: string;
}

export interface ExpertTool {
  name: string;
  label?: string;
  description: string;
  category: string;
  requires_approval: boolean;
}

export async function listExperts(): Promise<{ items: any[]; total: number }> {
  const response = await client.get('/v1/experts');
  return response.data;
}

export async function defineExpert(request: ExpertDefineRequest): Promise<any> {
  const response = await client.post('/v1/experts', request);
  return response.data;
}

export async function runExpert(expertName: string, task: string): Promise<any> {
  const response = await client.post('/v1/experts/run', { expert_name: expertName, task });
  return response.data;
}

export async function listAvailableTools(): Promise<{ tools: ExpertTool[]; total: number }> {
  const response = await client.get('/v1/experts/available-tools');
  return response.data;
}

export async function listApprovals(): Promise<{ pending: any[]; history: any[] }> {
  const response = await client.get('/v1/experts/approvals');
  return response.data;
}

export async function decideApproval(requestId: string, approved: boolean, comment?: string): Promise<any> {
  const response = await client.post(`/v1/experts/approvals/${requestId}`, { approved, comment });
  return response.data;
}
