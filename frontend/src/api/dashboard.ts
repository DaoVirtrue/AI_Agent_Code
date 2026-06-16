import client from './client';

export interface DashboardStats {
  totalTokens: number;
  totalCost: number;
  activeModels: number;
  healthStatus: string;
}

export interface TokenTrend {
  date: string;
  input: number;
  output: number;
}

export interface ModelDistribution {
  model: string;
  tokens: number;
}

export interface CostTrend {
  date: string;
  cost: number;
}

export async function fetchDashboardStats(): Promise<DashboardStats> {
  const response = await client.get<DashboardStats>('/v1/dashboard/stats');
  return response.data;
}

export async function fetchTokenTrend(): Promise<TokenTrend[]> {
  const response = await client.get<TokenTrend[]>('/v1/dashboard/trend');
  return response.data;
}

export async function fetchModelDistribution(): Promise<ModelDistribution[]> {
  const response = await client.get<ModelDistribution[]>('/v1/dashboard/distribution');
  return response.data;
}

export async function fetchCostTrend(): Promise<CostTrend[]> {
  const response = await client.get<CostTrend[]>('/v1/dashboard/costs');
  return response.data;
}
