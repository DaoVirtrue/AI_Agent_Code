import client from './client';
import { ModelInfo } from '@/types';

export interface ProviderHealth {
  provider: string;
  status: 'healthy' | 'degraded' | 'unhealthy';
  latency: number;
  successRate: number;
}

export async function listModels(): Promise<ModelInfo[]> {
  const response = await client.get<ModelInfo[]>('/v1/gateway/models');
  return response.data;
}

export async function getProviderHealth(): Promise<ProviderHealth[]> {
  const response = await client.get<ProviderHealth[]>('/v1/gateway/health');
  return response.data;
}
