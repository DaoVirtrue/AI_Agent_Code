import client from './client';
import { RenderRequest, RenderResponse, TemplateCreate, TemplateResponse } from '@/types';

export async function renderPrompt(request: RenderRequest): Promise<RenderResponse> {
  const response = await client.post<RenderResponse>('/v1/prompts/render', request);
  return response.data;
}

export async function listTemplates(): Promise<TemplateResponse[]> {
  const response = await client.get<TemplateResponse[]>('/v1/prompts/templates');
  return response.data;
}

export async function createTemplate(request: TemplateCreate): Promise<TemplateResponse> {
  const response = await client.post<TemplateResponse>('/v1/prompts/templates', request);
  return response.data;
}
