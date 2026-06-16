import client from './client';
import { LoginRequest, LoginResponse } from '@/types/auth';

function createMockJwt(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const body = btoa(JSON.stringify({ ...payload, exp: Math.floor(Date.now() / 1000) + 86400 }));
  const signature = btoa('mock-signature');
  return `${header}.${body}.${signature}`;
}

export async function login(
  username: string,
  password: string
): Promise<LoginResponse> {
  // Mock login for development — admin/admin works
  if (username === 'admin' && password === 'admin') {
    const user = {
      id: 'usr_001',
      username: 'admin',
      role: 'admin' as const,
      tenant_id: 'tenant_default',
    };
    const accessToken = createMockJwt({
      sub: user.id,
      username: user.username,
      role: user.role,
      tenant_id: user.tenant_id,
    });
    const refreshToken = createMockJwt({
      sub: user.id,
      type: 'refresh',
      exp: Math.floor(Date.now() / 1000) + 604800,
    });

    return {
      access_token: accessToken,
      refresh_token: refreshToken,
      token_type: 'bearer',
      user,
    };
  }

  // Real API call fallback
  const request: LoginRequest = { username, password };
  const response = await client.post<LoginResponse>('/v1/auth/login', request);
  return response.data;
}

export async function refreshToken(): Promise<LoginResponse> {
  const response = await client.post<LoginResponse>('/v1/auth/refresh');
  return response.data;
}

export async function logout(): Promise<void> {
  try {
    await client.post('/v1/auth/logout');
  } catch {
    // Swallow — we clear tokens client-side regardless
  }
}

export async function getCurrentUser(): Promise<LoginResponse['user']> {
  const response = await client.get<LoginResponse['user']>('/v1/auth/me');
  return response.data;
}
