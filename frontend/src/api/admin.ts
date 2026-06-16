import client from './client';

export interface TenantInfo {
  id: string;
  name: string;
  tier: string;
  userCount: number;
  createdAt: string;
}

export async function listTenants(): Promise<TenantInfo[]> {
  const response = await client.get<TenantInfo[]>('/v1/admin/tenants');
  return response.data;
}

export async function getAuditLogs(params: { page?: number; pageSize?: number }): Promise<{
  items: any[];
  total: number;
}> {
  const response = await client.get('/v1/admin/audit', { params });
  return response.data;
}
