import { create } from 'zustand';
import type { User } from '@/types';
import { setToken, removeToken, getToken, isTokenExpired } from '@/utils/token';
import { login as loginApi } from '@/api/auth';

// ---- Mock JWT token for demo (valid for 1 year) ----
function makeMockJwt(): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const payload = btoa(
    JSON.stringify({
      sub: 'user_demo',
      username: 'admin',
      role: 'admin',
      tenant_id: 't_1',
      exp: Math.floor(Date.now() / 1000) + 31536000,
      iat: Math.floor(Date.now() / 1000),
    })
  );
  const signature = btoa('demo_signature');
  return `${header}.${payload}.${signature}`;
}

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  login: (username: string, password: string) => Promise<boolean>;
  logout: () => Promise<void>;
  checkAuth: () => Promise<void>;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  token: getToken(),
  isAuthenticated: !!getToken(),
  isLoading: false,
  error: null,

  login: async (username: string, password: string) => {
    set({ isLoading: true, error: null });
    try {
      if (!username || !password) {
        throw new Error('请输入用户名和密码');
      }

      // 真实登录：调用后端 /v1/auth/login，返回 demo API key
      const response = await loginApi(username, password);
      const accessToken = response.access_token || 'demo-jwt-token';

      const user: User = {
        id: 'user_demo',
        username: response.username || username,
        role: (response.role as any) || 'admin',
        tenant_id: 't_1',
      };

      setToken(accessToken);
      set({
        user,
        token: accessToken,
        isAuthenticated: true,
        isLoading: false,
        error: null,
      });
      return true;
    } catch (err) {
      const message =
        err instanceof Error ? err.message : '登录失败，请重试。';
      set({
        isLoading: false,
        error: message,
        isAuthenticated: false,
      });
      return false;
    }
  },

  logout: async () => {
    // MOCK: Client-side logout only, no API call
    removeToken();
    set({
      user: null,
      token: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,
    });
  },

  checkAuth: async () => {
    const existingToken = getToken();
    if (!existingToken || isTokenExpired(existingToken)) {
      if (isTokenExpired(existingToken ?? undefined)) {
        removeToken();
      }
      set({ user: null, token: null, isAuthenticated: false });
      return;
    }

    set({ token: existingToken, isAuthenticated: true });

    try {
      // Decode user from JWT payload (no API call — avoids 401 interceptor logout)
      const payload = JSON.parse(atob(existingToken.split('.')[1]));
      set({ user: { id: payload.sub, username: payload.username, role: payload.role, tenant_id: payload.tenant_id }, isAuthenticated: true });
    } catch {
      // Keep isAuthenticated based on token presence even if decode fails
    }
  },

  clearError: () => set({ error: null }),
}));
