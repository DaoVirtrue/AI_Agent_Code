import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  getToken,
  getRefreshToken,
  setToken,
  removeToken,
  isTokenExpired,
  getTokenPayload,
} from '@/utils/token';

// Helper: create a JWT string (header.payload.signature) for testing
// Uses btoa which produces standard base64; the decodeJwtPayload function handles
// base64url conversion internally (replacing - with + and _ with /).
function createTestJwt(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const body = btoa(JSON.stringify(payload));
  const signature = btoa('mock-signature');
  return `${header}.${body}.${signature}`;
}

// Create a JWT that expires at a given Unix timestamp (seconds)
function createJwtWithExp(expTimestamp: number): string {
  return createTestJwt({ exp: expTimestamp, sub: 'user1', role: 'admin' });
}

// Create a valid non-expired JWT (24 hours from now)
function createValidJwt(): string {
  const futureExp = Math.floor(Date.now() / 1000) + 86400;
  return createJwtWithExp(futureExp);
}

// Create an expired JWT (24 hours ago)
function createExpiredJwt(): string {
  const pastExp = Math.floor(Date.now() / 1000) - 86400;
  return createJwtWithExp(pastExp);
}

describe('tokenUtils - Token 工具函数', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  describe('setToken', () => {
    it('setToken 将访问令牌存储到 localStorage', () => {
      setToken('access-token-123');

      expect(localStorage.getItem('llm_platform_access_token')).toBe('access-token-123');
    });

    it('setToken 同时存储访问令牌和刷新令牌', () => {
      setToken('access-token-abc', 'refresh-token-xyz');

      expect(localStorage.getItem('llm_platform_access_token')).toBe('access-token-abc');
      expect(localStorage.getItem('llm_platform_refresh_token')).toBe('refresh-token-xyz');
    });

    it('setToken 只更新访问令牌时不删除已有的刷新令牌', () => {
      localStorage.setItem('llm_platform_refresh_token', 'existing-refresh');

      setToken('new-access-token');

      expect(localStorage.getItem('llm_platform_access_token')).toBe('new-access-token');
      expect(localStorage.getItem('llm_platform_refresh_token')).toBe('existing-refresh');
    });

    it('setToken 可以覆盖旧的访问令牌', () => {
      setToken('token-v1');
      setToken('token-v2');

      expect(localStorage.getItem('llm_platform_access_token')).toBe('token-v2');
    });
  });

  describe('getToken', () => {
    it('getToken 获取已存储的访问令牌', () => {
      localStorage.setItem('llm_platform_access_token', 'my-token-value');

      expect(getToken()).toBe('my-token-value');
    });

    it('getToken 在 localStorage 为空时返回 null', () => {
      expect(getToken()).toBeNull();
    });

    it('getToken 在 localStorage 中无该键时返回 null', () => {
      localStorage.setItem('some_other_key', 'other-value');

      expect(getToken()).toBeNull();
    });
  });

  describe('getRefreshToken', () => {
    it('getRefreshToken 获取已存储的刷新令牌', () => {
      localStorage.setItem('llm_platform_refresh_token', 'refresh-token');

      expect(getRefreshToken()).toBe('refresh-token');
    });

    it('getRefreshToken 在未设置刷新令牌时返回 null', () => {
      expect(getRefreshToken()).toBeNull();
    });
  });

  describe('removeToken', () => {
    it('removeToken 清除访问令牌和刷新令牌', () => {
      localStorage.setItem('llm_platform_access_token', 'access');
      localStorage.setItem('llm_platform_refresh_token', 'refresh');

      removeToken();

      expect(localStorage.getItem('llm_platform_access_token')).toBeNull();
      expect(localStorage.getItem('llm_platform_refresh_token')).toBeNull();
    });

    it('removeToken 在 localStorage 为空时不会抛出异常', () => {
      expect(() => removeToken()).not.toThrow();
    });
  });

  describe('isTokenExpired', () => {
    it('isTokenExpired 对 null 令牌返回 true', () => {
      expect(isTokenExpired(null)).toBe(true);
    });

    it('isTokenExpired 对 undefined 令牌返回 true', () => {
      expect(isTokenExpired(undefined)).toBe(true);
    });

    it('isTokenExpired 对空字符串返回 true（空字符串不是有效 JWT）', () => {
      expect(isTokenExpired('')).toBe(true);
    });

    it('isTokenExpired 对有效的未过期 JWT 返回 false', () => {
      const token = createValidJwt();

      expect(isTokenExpired(token)).toBe(false);
    });

    it('isTokenExpired 对已过期的 JWT 返回 true', () => {
      const token = createExpiredJwt();

      expect(isTokenExpired(token)).toBe(true);
    });

    it('isTokenExpired 在未传令牌时从 localStorage 读取令牌', () => {
      const token = createValidJwt();
      localStorage.setItem('llm_platform_access_token', token);

      expect(isTokenExpired()).toBe(false);
    });

    it('isTokenExpired 当传入的令牌覆盖 localStorage 中的令牌', () => {
      const validToken = createValidJwt();
      const expiredToken = createExpiredJwt();
      localStorage.setItem('llm_platform_access_token', validToken);

      // Even though localStorage has a valid token, the expired argument takes precedence
      expect(isTokenExpired(expiredToken)).toBe(true);
    });

    it('isTokenExpired 对没有 exp 字段的 JWT 返回 true', () => {
      const token = createTestJwt({ sub: 'user1', role: 'admin' }); // no exp

      expect(isTokenExpired(token)).toBe(true);
    });

    it('isTokenExpired 对格式错误的令牌返回 true', () => {
      expect(isTokenExpired('not-a-valid-jwt')).toBe(true);
    });
  });

  describe('getTokenPayload', () => {
    it('getTokenPayload 返回 JWT 的解析后的负载内容', () => {
      const token = createTestJwt({ sub: 'user1', role: 'admin', exp: 9999999999 });

      const payload = getTokenPayload(token);

      expect(payload).not.toBeNull();
      expect(payload!.sub).toBe('user1');
      expect(payload!.role).toBe('admin');
      expect(payload!.exp).toBe(9999999999);
    });

    it('getTokenPayload 对 null 令牌返回 null', () => {
      expect(getTokenPayload(null)).toBeNull();
    });

    it('getTokenPayload 在未传令牌时从 localStorage 读取', () => {
      const token = createTestJwt({ sub: 'localuser', role: 'viewer' });
      localStorage.setItem('llm_platform_access_token', token);

      const payload = getTokenPayload();

      expect(payload).not.toBeNull();
      expect(payload!.sub).toBe('localuser');
    });

    it('getTokenPayload 对无效令牌返回 null', () => {
      expect(getTokenPayload('garbage')).toBeNull();
    });
  });
});
