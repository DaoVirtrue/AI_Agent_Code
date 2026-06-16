export interface RenderRequest {
  template_id?: string;
  template_content?: string;
  variables: Record<string, string>;
  model?: string;
  tenant_id?: string;
}

export interface RenderResponse {
  rendered: string;
  template_id?: string;
  variables_used: string[];
  token_count: number;
}

export interface TemplateCreate {
  name: string;
  description?: string;
  content: string;
  variables: string[];
  category?: string;
  tags?: string[];
}

export interface TemplateResponse {
  id: string;
  name: string;
  description?: string;
  content: string;
  variables: string[];
  category?: string;
  tags?: string[];
  created_at: string;
  updated_at: string;
  version: number;
}

export interface ExperimentRequest {
  template_id: string;
  variable_sets: Record<string, string>[];
  model?: string;
  tenant_id?: string;
}
