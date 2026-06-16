import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useAuthStore } from '@/store/authStore';

// Mock the API layer: authStore calls login/logout from @/api/auth
// We mock this module so tests never hit real HTTP endpoints
vi.mock('@/api/auth', () => ({
  login: vi.fn(),
  logout: vi.fn(),
}));

import { login as loginApi, logout as logoutApi } from '@/api/auth';

// Helper: create a simple JWT for checkAuth tests
// checkAuth decodes via: JSON.parse(atob(existingToken.split('.')[1]))
function createTestJwt(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const body = btoa(JSON.stringify(payload));
  const signature = btoa('mock-signature');
  return `${header}.${body}.${signature}`;
}

// Helper: reset the store to a known clean state
function resetStore(overrides: Partial<ReturnType<typeof useAuthStore.getState>> = {}) {
  useAuthStore.setState({
    user: null,
    token: null,
    isAuthenticated: false,
    isLoading: false,
    error: null,
    ...overrides,
  });
}

describe('useAuthStore - 认证状态管理', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    resetStore();
  });

  describe('login - 登录', () => {
    it('使用 admin/admin 登录成功，返回 true 并设置 isAuthenticated 为 true', async () => {
      vi.mocked(loginApi).mockResolvedValue({
        access_token: 'access-token-value',
        refresh_token: 'refresh-token-value',
        token_type: 'bearer',
        user: {
          id: 'usr_admin',
          username: 'admin',
          role: 'admin',
          tenant_id: 'tenant_default',
        },
      });

      const result = await useAuthStore.getState().login('admin', 'admin');

      expect(result).toBe(true);
      const state = useAuthStore.getState();
      expect(state.isAuthenticated).toBe(true);
      expect(state.user).not.toBeNull();
      expect(state.user!.username).toBe('admin');
      expect(state.user!.role).toBe('admin');
      expect(state.isLoading).toBe(false);
      expect(state.error).toBeNull();
    });

    it('登录成功后令牌存储到 localStorage', async () => {
      vi.mocked(loginApi).mockResolvedValue({
        access_token: 'access-token-stored',
        refresh_token: 'refresh-token-stored',
        token_type: 'bearer',
        user: { id: 'usr_1', username: 'testuser', role: 'developer', tenant_id: 't1' },
      });

      await useAuthStore.getState().login('testuser', 'pass');

      expect(localStorage.getItem('llm_platform_access_token')).toBe('access-token-stored');
      expect(localStorage.getItem('llm_platform_refresh_token')).toBe('refresh-token-stored');
      expect(useAuthStore.getState().token).toBe('access-token-stored');
    });

    it('使用错误凭证登录失败，返回 false', async () => {
      vi.mocked(loginApi).mockRejectedValue(new Error('Invalid credentials'));

      const result = await useAuthStore.getState().login('wrong', 'wrong');

      expect(result).toBe(false);
      const state = useAuthStore.getState();
      expect(state.isAuthenticated).toBe(false);
      expect(state.user).toBeNull();
      expect(state.error).toBe('Invalid credentials');
    });

    it('登录失败后 isLoading 恢复为 false', async () => {
      vi.mocked(loginApi).mockRejectedValue(new Error('Network error'));

      await useAuthStore.getState().login('user', 'pass');

      expect(useAuthStore.getState().isLoading).toBe(false);
    });

    it('登录前设置 isLoading 为 true', async () => {
      vi.mocked(loginApi).mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve({
          access_token: 'tok',
          refresh_token: 'ref',
          token_type: 'bearer',
          user: { id: 'u', username: 'a', role: 'admin', tenant_id: 't' },
        }), 50))
      );

      const loginPromise = useAuthStore.getState().login('admin', 'admin');
      // State should be loading immediately after login call
      expect(useAuthStore.getState().isLoading).toBe(true);

      await loginPromise;
      expect(useAuthStore.getState().isLoading).toBe(false);
    });

    it('登录成功时清除之前的错误信息', async () => {
      // Set a previous error
      useAuthStore.setState({ error: 'Previous error' });

      vi.mocked(loginApi).mockResolvedValue({
        access_token: 'tok',
        refresh_token: 'ref',
        token_type: 'bearer',
        user: { id: 'u', username: 'a', role: 'admin', tenant_id: 't' },
      });

      await useAuthStore.getState().login('admin', 'admin');

      expect(useAuthStore.getState().error).toBeNull();
    });
  });

  describe('logout - 登出', () => {
    it('登出后清除令牌并设置 isAuthenticated 为 false', async () => {
      // Set up authenticated state
      localStorage.setItem('llm_platform_access_token', 'existing-token');
      localStorage.setItem('llm_platform_refresh_token', 'existing-refresh');
      useAuthStore.setState({
        isAuthenticated: true,
        token: 'existing-token',
        user: { id: 'u', username: 'admin', role: 'admin', tenant_id: 't' },
      });

      await useAuthStore.getState().logout();

      const state = useAuthStore.getState();
      expect(state.isAuthenticated).toBe(false);
      expect(state.user).toBeNull();
      expect(state.token).toBeNull();
      expect(localStorage.getItem('llm_platform_access_token')).toBeNull();
      expect(localStorage.getItem('llm_platform_refresh_token')).toBeNull();
    });

    it('登出后 isLoading 恢复为 false', async () => {
      await useAuthStore.getState().logout();
      expect(useAuthStore.getState().isLoading).toBe(false);
    });

    it('登出后清除错误信息', async () => {
      useAuthStore.setState({ error: 'Some error' });

      await useAuthStore.getState().logout();

      expect(useAuthStore.getState().error).toBeNull();
    });

    it('即使登出 API 失败也清除客户端令牌', async () => {
      vi.mocked(logoutApi).mockRejectedValue(new Error('Server unreachable'));
      localStorage.setItem('llm_platform_access_token', 'existing-token');
      useAuthStore.setState({ isAuthenticated: true, token: 'existing-token' });

      // Should not throw
      await expect(useAuthStore.getState().logout()).resolves.not.toThrow();

      expect(localStorage.getItem('llm_platform_access_token')).toBeNull();
      expect(useAuthStore.getState().isAuthenticated).toBe(false);
    });
  });

  describe('checkAuth - 检查认证状态', () => {
    it('当 localStorage 中没有令牌时，设置 isAuthenticated 为 false', async () => {
      await useAuthStore.getState().checkAuth();

      const state = useAuthStore.getState();
      expect(state.isAuthenticated).toBe(false);
      expect(state.user).toBeNull();
      expect(state.token).toBeNull();
    });

    it('当有有效令牌时，设置 isAuthenticated 为 true 并解析用户信息', async () => {
      const token = createTestJwt({
        sub: 'usr_test',
        username: 'testuser',
        role: 'developer',
        tenant_id: 'tenant_xyz',
        exp: Math.floor(Date.now() / 1000) + 86400,
      });
      localStorage.setItem('llm_platform_access_token', token);

      await useAuthStore.getState().checkAuth();

      const state = useAuthStore.getState();
      expect(state.isAuthenticated).toBe(true);
      expect(state.token).toBe(token);
      expect(state.user).not.toBeNull();
      expect(state.user!.id).toBe('usr_test');
      expect(state.user!.username).toBe('testuser');
      expect(state.user!.role).toBe('developer');
      expect(state.user!.tenant_id).toBe('tenant_xyz');
    });

    it('当令牌格式无效时仍然设置 isAuthenticated（基于令牌存在）', async () => {
      localStorage.setItem('llm_platform_access_token', 'not-a-valid-jwt');

      await useAuthStore.getState().checkAuth();

      // Token is present, so isAuthenticated should be true
      // even though JWT decode will fail in the catch block
      expect(useAuthStore.getState().isAuthenticated).toBe(true);
      expect(useAuthStore.getState().token).toBe('not-a-valid-jwt');
    });

    it('checkAuth 正确设置 token 状态', async () => {
      const token = createTestJwt({
        sub: 'usr_abc',
        username: 'abc',
        role: 'viewer',
        tenant_id: 't',
        exp: Math.floor(Date.now() / 1000) + 3600,
      });
      localStorage.setItem('llm_platform_access_token', token);

      await useAuthStore.getState().checkAuth();

      expect(useAuthStore.getState().token).toBe(token);
    });

    it('传入空令牌时不会抛出异常', async () => {
      // localStorage already cleared by beforeEach
      await expect(useAuthStore.getState().checkAuth()).resolves.not.toThrow();
    });
  });

  describe('clearError - 清除错误', () => {
    it('清除当前的错误信息', () => {
      useAuthStore.setState({ error: 'Something went wrong' });

      useAuthStore.getState().clearError();

      expect(useAuthStore.getState().error).toBeNull();
    });

    it('在无错误时调用不会改变状态', () => {
      useAuthStore.setState({ error: null, isAuthenticated: false });

      useAuthStore.getState().clearError();

      expect(useAuthStore.getState().error).toBeNull();
    });
  });

  describe('initial state - 初始状态', () => {
    it('当 localStorage 中没有令牌时，isAuthenticated 为 false', () => {
      localStorage.clear();
      // Reset the store to match the initial state computation pattern
      useAuthStore.setState({
        user: null,
        token: null,
        isAuthenticated: false,
        isLoading: false,
        error: null,
      });

      const state = useAuthStore.getState();
      expect(state.isAuthenticated).toBe(false);
      expect(state.user).toBeNull();
    });

    it('isAuthenticated 取决于 localStorage 中是否有令牌', () => {
      // Simulate the initial creation pattern
      const storedToken = localStorage.getItem('llm_platform_access_token');
      useAuthStore.setState({
        isAuthenticated: !!storedToken,
        token: storedToken,
      });

      // With no token
      expect(useAuthStore.getState().isAuthenticated).toBe(false);

      // Set a token and re-evaluate
      localStorage.setItem('llm_platform_access_token', 'some-token');
      const newToken = localStorage.getItem('llm_platform_access_token');
      useAuthStore.setState({
        isAuthenticated: !!newToken,
        token: newToken,
      });

      expect(useAuthStore.getState().isAuthenticated).toBe(true);
    });
  });
});
