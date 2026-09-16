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
  // 真实登录：调用后端 /v1/auth/login
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
