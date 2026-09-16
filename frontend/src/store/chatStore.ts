import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { getBestChunks, searchDocuments } from '@/utils/ragSearch';
import { syncMemory } from '@/api/chat';
import type { SourceDoc, AgentStep, TokenUsage, MessageDict } from '@/types';

const DEFAULT_MODEL = 'deepseek-chat';
let msgIdCounter = 0;
function generateMessageId() { return `msg_${Date.now()}_${++msgIdCounter}`; }

export interface ChatMessage extends MessageDict {
  id?: string; model?: string; latencyMs?: number; timestamp?: string; tokenUsage?: TokenUsage;
}
export interface Conversation {
  id: string; title: string; messages: ChatMessage[]; model: string;
  createdAt: string; updatedAt: string; sources?: SourceDoc[]; agentSteps?: AgentStep[];
}

interface ChatState {
  conversations: Conversation[];
  activeConversationId: string | null;
  isStreaming: boolean; isLoading: boolean; error: string | null; selectedModel: string;
  createConversation: (title?: string, model?: string) => string;
  deleteConversation: (id: string) => void;
  setActiveConversation: (id: string) => void;
  sendMessage: (content: string, model?: string, expertName?: string) => Promise<void>;
}

export const useChatStore = create<ChatState>()(persist((set, get) => ({
  conversations: [], activeConversationId: null, isStreaming: false, isLoading: false, error: null, selectedModel: DEFAULT_MODEL,

  createConversation: (title, model) => {
    const id = `conv_${Date.now()}`;
    const conv: Conversation = { id, title: title || '新对话', model: model || DEFAULT_MODEL, messages: [], createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() };
    set(s => ({ conversations: [conv, ...s.conversations], activeConversationId: id, error: null }));
    return id;
  },
  deleteConversation: (id) => set(s => {
    const f = s.conversations.filter(c => c.id !== id);
    return { conversations: f, activeConversationId: s.activeConversationId === id ? (f[0]?.id || null) : s.activeConversationId };
  }),
  setActiveConversation: (id) => set({ activeConversationId: id, error: null }),

  sendMessage: async (content, model, expertName?) => {
    const state = get();
    if (state.isStreaming || !content.trim()) return;
    let conv = state.conversations.find(c => c.id === state.activeConversationId);
    if (!conv) { get().createConversation(undefined, model); conv = get().conversations.find(c => c.id === get().activeConversationId); }
    if (!conv) return;

    const requestModel = model || conv.model || DEFAULT_MODEL;
    const convId = conv.id;
    const userMsg: ChatMessage = { id: generateMessageId(), role: 'user', content: content.trim(), timestamp: new Date().toISOString() };
    const assistantMsg: ChatMessage = { id: generateMessageId(), role: 'assistant', content: '', model: requestModel, timestamp: new Date().toISOString() };
    const updatedMessages = [...conv.messages, userMsg, assistantMsg];

    set(s => ({
      conversations: s.conversations.map(c => c.id === convId ? { ...c, messages: updatedMessages, model: requestModel, title: c.messages.length === 0 ? content.trim().slice(0, 30) : c.title, updatedAt: new Date().toISOString() } : c),
      isStreaming: true, isLoading: false, error: null,
    }));

    // Sync user message to backend conversation memory (STM + compression).
    syncMemory(convId, 'user', content.trim()).catch(() => {});

    try {
      // 指定专家 -> 走专家运行端点（带专属知识库+技能+MCP）
      if (expertName) {
        const { runExpert } = await import('@/api/experts');
        const expertResult = await runExpert(expertName, content.trim());
        const reply = expertResult.output || '(无回复)';
        set(s => ({
          conversations: s.conversations.map(c => {
            if (c.id !== convId) return c;
            const msgs = [...c.messages]; const last = msgs[msgs.length - 1];
            if (last?.role === 'assistant') {
              last.content = reply;
              last.tokenUsage = { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 };
            }
            return { ...c, messages: msgs, updatedAt: new Date().toISOString() };
          }),
          isStreaming: false,
        }));
        syncMemory(convId, 'assistant', reply).catch(() => {});
        return;
      }

      // RAG search with TF-IDF scoring
      const ragDocs = (() => { try { return JSON.parse(localStorage.getItem('llm_platform_rag_documents') || '[]'); } catch { return []; } })();
      let ragContext = '';
      if (ragDocs.length > 0) {
        const bestChunks = getBestChunks(content, ragDocs, 3);
        if (bestChunks.length > 0) {
          ragContext = '\n\n【知识库参考内容】\n' + bestChunks.map((c: string, i: number) => `[文档片段${i+1}] ${c.substring(0, 500)}...`).join('\n\n') + '\n请基于以上参考内容回答用户问题。';
        }
        console.log('RAG: found', bestChunks.length, 'chunks from', ragDocs.length, 'docs');
      }

      const apiMessages = [
        { role: 'system', content: '你是AI助手。对于复杂问题请用格式：\n## 思考\n(推理)\n## 回答\n(结论)\n简单问题直接答。' + ragContext },
        ...updatedMessages.filter(m => m.content && m.content.trim()).map(m => ({ role: m.role, content: m.content })),
      ];
      const response = await fetch('/api/v1/chat/completions', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: requestModel, messages: apiMessages, max_tokens: 8192, stream: true }),
      });
      if (!response.ok) throw new Error(`API ${response.status}`);

      // SSE streaming: read chunks and update assistant message content incrementally
      const reader = response.body?.getReader();
      let reply = '';
      let usage: any = {};
      if (reader) {
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';
          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed.startsWith('data: ')) continue;
            const dataStr = trimmed.slice(6);
            if (dataStr === '[DONE]') continue;
            try {
              const chunk = JSON.parse(dataStr);
              const delta = chunk.choices?.[0]?.delta?.content || '';
              reply += delta;
              if (chunk.usage) usage = chunk.usage;
              // Update UI with streaming content
              set(s => ({
                conversations: s.conversations.map(c => {
                  if (c.id !== convId) return c;
                  const msgs = [...c.messages]; const last = msgs[msgs.length - 1];
                  if (last?.role === 'assistant') last.content = reply;
                  return { ...c, messages: msgs, updatedAt: new Date().toISOString() };
                }),
              }));
            } catch {}
          }
        }
      }
      if (!reply) reply = '(无回复)';

      // Sync assistant reply to backend conversation memory.
      syncMemory(convId, 'assistant', reply).catch(() => {});

      // Search real RAG document chunks for sources
      const sources: SourceDoc[] = (() => {
        try {
          const docs: any[] = JSON.parse(localStorage.getItem('llm_platform_rag_documents') || '[]');
          const kw = content.split(/[\s,，。！？、；：]+/).filter((k: string) => k.length > 0).map((k: string) => k.toLowerCase());
          if (docs.length === 0 || kw.length === 0) return [];
          const hits: any[] = [];
          docs.forEach((doc: any) => {
            (doc.chunks || []).forEach((chunk: string, idx: number) => {
              const lower = chunk.toLowerCase();
              let matches = 0;
              kw.forEach((k: string) => { if (lower.includes(k)) matches++; });
              const score = matches / kw.length;
              if (score > 0) hits.push({ doc, chunk, idx, score });
            });
          });
          return hits.sort((a, b) => b.score - a.score).slice(0, 5).map(h => ({
            chunk_id: `${h.doc.document_id}_${h.idx}`,
            document_name: h.doc.filename,
            content: h.chunk.substring(0, 300),
            score: h.score,
          }));
        } catch { return []; }
      })();

      // Parse thinking steps from response
      const steps: AgentStep[] = [];
      const thinkMatch = reply.match(/##\s*思考\n?([\s\S]*?)(?=##\s*回答|$)/i);
      if (thinkMatch) {
        const thinking = thinkMatch[1].trim();
        const sentences = thinking.split(/[。！？\n]+/).filter((s: string) => s.trim().length > 10);
        sentences.forEach((s: string, i: number) => {
          steps.push({ step_number: i+1, type: 'thought', content: s.trim(), thought: s.trim(), action: '', observation: '', tool_name: '', tool_input: '', tool_output: '', elapsed_ms: 0, tokens_used: 0 });
        });
      }
      steps.push({ step_number: steps.length+1, type: 'observation', content: `最终回答 (${usage.completion_tokens || 0} 输出 tokens)`, thought: '', action: '', observation: `生成最终回答，消耗 ${usage.completion_tokens || 0} tokens`, tool_name: '', tool_input: '', tool_output: '', elapsed_ms: 0, tokens_used: 0 });

      set(s => ({
        conversations: s.conversations.map(c => {
          if (c.id !== convId) return c;
          const msgs = [...c.messages]; const last = msgs[msgs.length - 1];
          if (last?.role === 'assistant') {
            last.content = reply;
            last.tokenUsage = { prompt_tokens: usage.prompt_tokens || 0, completion_tokens: usage.completion_tokens || 0, total_tokens: usage.total_tokens || 0 };
          }
          return { ...c, messages: msgs, sources, agentSteps: steps, updatedAt: new Date().toISOString() };
        }),
        isStreaming: false,
      }));
    } catch (err: any) {
      set(s => ({
        conversations: s.conversations.map(c => {
          if (c.id !== convId) return c;
          const msgs = [...c.messages]; const last = msgs[msgs.length - 1];
          if (last?.role === 'assistant') last.content = '抱歉，API 调用失败: ' + (err.message || '未知错误');
          return { ...c, messages: msgs, updatedAt: new Date().toISOString() };
        }),
        isStreaming: false,
      }));
    }
  },
}), { name: 'llm-chat-store', storage: createJSONStorage(() => localStorage), partialize: (s) => ({ conversations: s.conversations, activeConversationId: s.activeConversationId }) }));
