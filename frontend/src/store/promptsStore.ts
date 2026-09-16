import { create } from 'zustand';
import type { TemplateCreate, TemplateResponse, RenderResponse } from '@/types';
import { listTemplates, renderPrompt, createTemplate } from '@/api/prompts';

// ---- Mock template data ----
const MOCK_TEMPLATES: TemplateResponse[] = [
  {
    id: 'tpl_1',
    name: '代码审查助手',
    description: '用于自动化代码审查的提示词模板，支持多种编程语言',
    content: '你是一位资深代码审查专家。请审查以下 {{language}} 代码，重点关注：\n1. 代码质量\n2. 安全漏洞\n3. 性能问题\n4. 最佳实践\n\n代码：\n{{code}}',
    variables: ['language', 'code'],
    category: '开发工具',
    tags: ['代码审查', '安全', '自动化'],
    created_at: '2026-06-01T08:00:00Z',
    updated_at: '2026-06-10T14:30:00Z',
    version: 3,
  },
  {
    id: 'tpl_2',
    name: '技术文档生成器',
    description: '根据代码注释和结构自动生成API文档',
    content: '你是一位技术文档撰写专家。请根据以下 {{language}} 代码生成详细的API文档，包括：\n- 函数签名\n- 参数说明\n- 返回值描述\n- 使用示例\n\n源代码：\n{{source_code}}',
    variables: ['language', 'source_code'],
    category: '文档',
    tags: ['文档', 'API', '自动化'],
    created_at: '2026-05-28T10:15:00Z',
    updated_at: '2026-06-08T09:45:00Z',
    version: 2,
  },
  {
    id: 'tpl_3',
    name: '客户邮件回复',
    description: '根据客户邮件内容自动生成专业回复',
    content: '你是客户支持专员。请根据以下客户邮件内容，撰写一封专业、友好、有帮助的回复。\n\n客户邮件：\n{{email_content}}\n\n回复要求：\n- 语气：{{tone}}\n- 字数限制：{{max_words}}字以内',
    variables: ['email_content', 'tone', 'max_words'],
    category: '客户服务',
    tags: ['邮件', '客户支持', '自动化回复'],
    created_at: '2026-05-20T16:00:00Z',
    updated_at: '2026-06-05T11:20:00Z',
    version: 4,
  },
];

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

interface VersionInfo {
  version: number;
  created_at: string;
}

interface ExperimentResult {
  variantName: string;
  avgScore: number;
  pValue: number;
  cohensD: number;
  winner: boolean;
}

interface PromptsState {
  templates: TemplateResponse[];
  templatesLoading: boolean;
  selectedTemplate: TemplateResponse | null;
  versions: VersionInfo[];
  versionsLoading: boolean;
  renderedOutput: string;
  renderedTokens: number;
  renderLoading: boolean;
  experiments: ExperimentResult[];
  experimentsLoading: boolean;
  error: string | null;

  fetchTemplates: (params?: { category?: string; search?: string }) => Promise<void>;
  fetchTemplateById: (id: string) => Promise<void>;
  fetchVersions: (id: string) => Promise<void>;
  createNewTemplate: (data: TemplateCreate) => Promise<TemplateResponse | null>;
  updateExistingTemplate: (id: string, data: Partial<TemplateCreate>) => Promise<void>;
  deleteExistingTemplate: (id: string) => Promise<void>;
  renderTemplate: (templateId: string, variables: Record<string, string>) => Promise<void>;
  runABExperiment: (templateId: string, variableSets: Record<string, string>[]) => Promise<void>;
  selectTemplate: (t: TemplateResponse | null) => void;
  clearError: () => void;
}

export const usePromptsStore = create<PromptsState>((set, get) => ({
  templates: [],
  templatesLoading: false,
  selectedTemplate: null,
  versions: [],
  versionsLoading: false,
  renderedOutput: '',
  renderedTokens: 0,
  renderLoading: false,
  experiments: [],
  experimentsLoading: false,
  error: null,

  fetchTemplates: async (params) => {
    set({ templatesLoading: true, error: null });
    try {
      const data = await listTemplates();
      const templates: TemplateResponse[] = Array.isArray(data) ? data : (data as any)?.items || [];
      let filtered = [...templates];
      if (params?.category) {
        filtered = filtered.filter((t) => (t as any).category === params.category);
      }
      if (params?.search) {
        const q = params.search.toLowerCase();
        filtered = filtered.filter(
          (t) => t.name.toLowerCase().includes(q) || (t.description || '').toLowerCase().includes(q)
        );
      }
      set({ templates: filtered, templatesLoading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch templates';
      set({ error: message, templatesLoading: false });
    }
  },

  fetchTemplateById: async (id: string) => {
    set({ error: null });
    try {
      // Find locally from already-loaded templates
      const existing = get().templates.find((t) => t.id === id);
      set({ selectedTemplate: existing || null });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch template';
      set({ error: message });
    }
  },

  fetchVersions: async (_id: string) => {
    set({ versionsLoading: true, error: null });
    try {
      set({ versions: [], versionsLoading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch versions';
      set({ error: message, versionsLoading: false });
    }
  },

  createNewTemplate: async (data) => {
    set({ error: null });
    try {
      // MOCK: Create template locally without API call
      const now = new Date().toISOString();
      const created: TemplateResponse = {
        id: `tpl_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
        name: data.name,
        description: data.description,
        content: data.content,
        variables: data.variables || [],
        category: data.category,
        tags: data.tags || [],
        created_at: now,
        updated_at: now,
        version: 1,
      };
      set((s) => ({ templates: [created, ...s.templates] }));
      return created;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create template';
      set({ error: message });
      return null;
    }
  },

  updateExistingTemplate: async (id, data) => {
    set({ error: null });
    try {
      set((s) => ({
        templates: s.templates.map((t) => (t.id === id ? { ...t, ...data } : t)),
        selectedTemplate: s.selectedTemplate?.id === id ? { ...s.selectedTemplate, ...data } : s.selectedTemplate,
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update template';
      set({ error: message });
    }
  },

  deleteExistingTemplate: async (id) => {
    try {
      set((s) => ({
        templates: s.templates.filter((t) => t.id !== id),
        selectedTemplate: s.selectedTemplate?.id === id ? null : s.selectedTemplate,
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete template';
      set({ error: message });
    }
  },

  renderTemplate: async (templateId, variables) => {
    set({ renderLoading: true, error: null });
    try {
      const result = await renderPrompt({
        template_name: templateId,
        variables: variables as any,
      } as any);
      set({
        renderedOutput: result.rendered || '',
        renderedTokens: result.token_count || 0,
        renderLoading: false,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Render failed';
      set({ error: message, renderLoading: false });
    }
  },

  runABExperiment: async (_templateId, variableSets) => {
    set({ experimentsLoading: true, error: null });
    try {
      const expResults: ExperimentResult[] = [];
      set({ experiments: expResults, experimentsLoading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Experiment failed';
      set({ error: message, experimentsLoading: false });
    }
  },

  selectTemplate: (t) => set({ selectedTemplate: t, renderedOutput: '', renderedTokens: 0, versions: [] }),
  clearError: () => set({ error: null }),
}));
