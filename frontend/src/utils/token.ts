const TOKEN_KEY = 'llm_platform_access_token';
const REFRESH_TOKEN_KEY = 'llm_platform_refresh_token';

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function getRefreshToken(): string | null {
  try {
    return localStorage.getItem(REFRESH_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(accessToken: string, refreshToken?: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, accessToken);
    if (refreshToken) {
      localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
    }
  } catch {
    // localStorage not available (private browsing, etc.)
  }
}

export function removeToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  } catch {
    // localStorage not available
  }
}

function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const base64Url = token.split('.')[1];
    if (!base64Url) return null;
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    );
    return JSON.parse(jsonPayload);
  } catch {
    return null;
  }
}

export function isTokenExpired(token?: string | null): boolean {
  const t = token || getToken();
  if (!t) return true;

  const payload = decodeJwtPayload(t);
  if (!payload || !payload.exp) return true;

  const exp = typeof payload.exp === 'number' ? payload.exp * 1000 : Date.now();
  return Date.now() >= exp;
}

export function getTokenPayload(token?: string | null): Record<string, unknown> | null {
  const t = token || getToken();
  if (!t) return null;
  return decodeJwtPayload(t);
}
