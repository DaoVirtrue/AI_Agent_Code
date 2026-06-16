export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

export interface User {
  id: string;
  username: string;
  role: 'admin' | 'developer' | 'viewer';
  tenant_id: string;
}
