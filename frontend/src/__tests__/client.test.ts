import { describe, it, expect, beforeEach, vi } from 'vitest';

// MUST mock @/utils/token BEFORE importing client.
// vitest hoists vi.mock() to the top of the file.
// Use vi.fn() directly inside the factory to avoid hoisting issues with
// module-level const declarations.

vi.mock('@/utils/token', () => ({
  getToken: vi.fn(),
  getRefreshToken: vi.fn(),
  setToken: vi.fn(),
  removeToken: vi.fn(),
  isTokenExpired: vi.fn(),
}));

// Import the mocked module so we can control return values in tests
import { getToken } from '@/utils/token';

// Now import client — the interceptors will use the mocked getToken
import client from '@/api/client';
import type { InternalAxiosRequestConfig } from 'axios';

// Typed helpers for mock control
const mockGetToken = vi.mocked(getToken);

// Extract the request interceptor onFulfilled handler from the axios instance.
// After axios.create() + interceptors.request.use(), the handler is stored in
// client.interceptors.request.handlers[0].fulfilled
function getRequestInterceptor(): (
  config: InternalAxiosRequestConfig,
) => InternalAxiosRequestConfig {
  const handlers = (
    client.interceptors.request as unknown as {
      handlers: Array<{
        fulfilled: (config: InternalAxiosRequestConfig) => InternalAxiosRequestConfig;
        rejected: (error: unknown) => unknown;
      }>;
    }
  ).handlers;

  if (!handlers || handlers.length === 0) {
    throw new Error('No request interceptor registered on the axios client');
  }
  return handlers[0].fulfilled;
}

function createMockConfig(
  overrides: Partial<InternalAxiosRequestConfig> = {},
): InternalAxiosRequestConfig {
  return {
    headers: { 'Content-Type': 'application/json' },
    method: 'get',
    url: '/test-endpoint',
    ...overrides,
  } as InternalAxiosRequestConfig;
}

describe('Axios Client 拦截器', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: no token in storage
    mockGetToken.mockReturnValue(null);
  });

  describe('请求拦截器 (Request Interceptor)', () => {
    it('当 getToken 返回令牌时，自动添加 Authorization 请求头', () => {
      mockGetToken.mockReturnValue('test-bearer-token-xyz');

      const interceptor = getRequestInterceptor();
      const config = createMockConfig();
      const result = interceptor(config);

      expect(result.headers).toBeDefined();
      expect((result.headers as Record<string, string>).Authorization).toBe(
        'Bearer test-bearer-token-xyz',
      );
    });

    it('当 getToken 返回 null 时，不添加 Authorization 请求头', () => {
      mockGetToken.mockReturnValue(null);

      const interceptor = getRequestInterceptor();
      const config = createMockConfig();
      const result = interceptor(config);

      const authHeader = (result.headers as Record<string, string>).Authorization;
      expect(authHeader).toBeUndefined();
    });

    it('当 token 为空字符串时不添加 Authorization 请求头', () => {
      mockGetToken.mockReturnValue('');

      const interceptor = getRequestInterceptor();
      const config = createMockConfig();
      const result = interceptor(config);

      // '' is falsy, so the interceptor should not add Authorization
      const authHeader = (result.headers as Record<string, string>).Authorization;
      expect(authHeader).toBeUndefined();
    });

    it('拦截器保留原始配置中的其他请求头', () => {
      mockGetToken.mockReturnValue('my-token');

      const interceptor = getRequestInterceptor();
      const config = createMockConfig({
        headers: {
          'Content-Type': 'application/json',
          'X-Custom-Header': 'custom-value',
        },
      });
      const result = interceptor(config);

      const headers = result.headers as Record<string, string>;
      expect(headers['Content-Type']).toBe('application/json');
      expect(headers['X-Custom-Header']).toBe('custom-value');
      expect(headers.Authorization).toBe('Bearer my-token');
    });

    it('不同的 token 值生成不同的 Authorization 请求头', () => {
      const interceptor = getRequestInterceptor();

      mockGetToken.mockReturnValue('token-v1');
      const result1 = interceptor(createMockConfig());
      expect((result1.headers as Record<string, string>).Authorization).toBe(
        'Bearer token-v1',
      );

      mockGetToken.mockReturnValue('token-v2');
      const result2 = interceptor(createMockConfig());
      expect((result2.headers as Record<string, string>).Authorization).toBe(
        'Bearer token-v2',
      );
    });

    it('拦截器返回的 config 对象包含原始 URL', () => {
      mockGetToken.mockReturnValue('some-token');

      const interceptor = getRequestInterceptor();
      const config = createMockConfig({ url: '/v1/chat/completions' });
      const result = interceptor(config);

      expect(result.url).toBe('/v1/chat/completions');
    });

    it('拦截器保留原始 method', () => {
      mockGetToken.mockReturnValue('tok');

      const interceptor = getRequestInterceptor();
      const config = createMockConfig({ method: 'post' });
      const result = interceptor(config);

      expect(result.method).toBe('post');
    });

    it('拦截器在 config.headers 为 undefined 时不会崩溃', () => {
      mockGetToken.mockReturnValue('some-token');

      const interceptor = getRequestInterceptor();
      // config with no headers at all
      const config = { method: 'get', url: '/test' } as InternalAxiosRequestConfig;
      const result = interceptor(config);

      // No headers to add Authorization to — should not throw
      expect(result).toBeDefined();
    });
  });

  describe('客户端实例配置', () => {
    it('客户端实例存在且是 axios 实例', () => {
      expect(client).toBeDefined();
      expect(typeof client.get).toBe('function');
      expect(typeof client.post).toBe('function');
      expect(typeof client.interceptors).toBe('object');
    });

    it('客户端配置了 baseURL', () => {
      expect(client.defaults.baseURL).toBe('/api');
    });

    it('客户端配置了超时时间', () => {
      expect(client.defaults.timeout).toBe(120_000);
    });

    it('客户端注册了请求拦截器', () => {
      const handlers = (
        client.interceptors.request as unknown as {
          handlers: Array<unknown>;
        }
      ).handlers;
      expect(handlers.length).toBeGreaterThanOrEqual(1);
    });

    it('客户端注册了响应拦截器', () => {
      const handlers = (
        client.interceptors.response as unknown as {
          handlers: Array<unknown>;
        }
      ).handlers;
      expect(handlers.length).toBeGreaterThanOrEqual(1);
    });

    it('客户端默认 Content-Type 为 application/json', () => {
      const headers = client.defaults.headers as Record<string, string>;
      expect(headers['Content-Type']).toBe('application/json');
    });
  });
});
