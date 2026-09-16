import client from './client';

export interface PermissionRule {
  tool_name: string;
  requires_approval: boolean;
  reason: string;
}

export async function listPermissions(): Promise<{ items: PermissionRule[]; total: number }> {
  const response = await client.get('/v1/permissions');
  return response.data;
}

export async function setPermission(toolName: string, requiresApproval: boolean, reason?: string): Promise<any> {
  const response = await client.post('/v1/permissions', {
    tool_name: toolName,
    requires_approval: requiresApproval,
    reason: reason || '',
  });
  return response.data;
}
