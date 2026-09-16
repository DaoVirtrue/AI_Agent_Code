import client from './client';

export interface Skill {
  skill_id: string;
  name: string;
  description: string;
  instructions: string;
  tools: string[];
  author: string;
  version: string;
}

export interface SkillCreateRequest {
  name: string;
  description?: string;
  instructions?: string;
  tools?: string[];
  author?: string;
  version?: string;
}

export async function listSkills(search?: string): Promise<{ items: Skill[]; total: number }> {
  const response = await client.get('/v1/skills', { params: search ? { search } : {} });
  return response.data;
}

export async function createSkill(request: SkillCreateRequest): Promise<any> {
  const response = await client.post('/v1/skills', request);
  return response.data;
}

export async function deleteSkill(name: string): Promise<any> {
  const response = await client.delete(`/v1/skills/${name}`);
  return response.data;
}

export async function installSkills(skills: string[]): Promise<{ instructions: string }> {
  const response = await client.post('/v1/skills/install', { skills });
  return response.data;
}
