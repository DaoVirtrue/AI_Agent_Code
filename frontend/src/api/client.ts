import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import { getToken, getRefreshToken, setToken, removeToken, isTokenExpired } from '@/utils/token';
import { API_BASE_URL } from '@/utils/constants';

const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120_000,
  headers: {
    'Content-Type': 'application/json',
  },
});

interface QueueItem {
  resolve: (token: string) => void;
  reject: (error: unknown) => void;
}

let isRefreshing = false;
let failedQueue: QueueItem[] = [];

function processQueue(error: unknown, token: string | null): void {
  failedQueue.forEach((item) => {
    if (error) {
      item.reject(error);
    } else if (token) {
      item.resolve(token);
    }
  });
  failedQueue = [];
}

client.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = getToken();
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

async function attemptTokenRefresh(): Promise<string> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    throw new Error('No refresh token available');
  }

  const response = await axios.post(`${API_BASE_URL}/v1/auth/refresh`, {
    refresh_token: refreshToken,
  });

  const { access_token, refresh_token: newRefreshToken } = response.data;
  setToken(access_token, newRefreshToken || refreshToken);
  return access_token;
}

client.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    // For demo/mock setup: backend has no real auth endpoints.
    // Don't try refresh/logout on 401 — just pass error to caller.
    // Each store handles API errors gracefully with mock data fallbacks.
    if (error.response?.status === 401) {
      // Only try refresh if we have a refresh token AND the failing request isn't auth-related
      const url = error.config?.url || '';
      const isAuthEndpoint = url.includes('/v1/auth/');
      if (!isAuthEndpoint && getRefreshToken()) {
        try {
          const newToken = await attemptTokenRefresh();
          if (newToken && error.config) {
            (error.config as any).headers.Authorization = 'Bearer ' + newToken;
            return client(error.config);
          }
        } catch {
          // Refresh failed — just continue, don't logout
        }
      }
    }
    return Promise.reject(error);
  }
);

export default client;
