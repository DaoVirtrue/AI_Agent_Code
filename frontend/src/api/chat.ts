import client from './client';
import { ChatRequest, ChatResponse } from '@/types';

export async function sendChatMessage(
  request: ChatRequest
): Promise<ChatResponse> {
  const response = await client.post<ChatResponse>('/v1/chat/completions', {
    ...request,
    stream: false,
  });
  return response.data;
}

export async function syncMemory(conversationId: string, role: string, content: string): Promise<any> {
  const response = await client.post('/v1/chat/memory/sync', {
    conversation_id: conversationId,
    role,
    content,
  });
  return response.data;
}

export async function getMemoryState(conversationId: string): Promise<any> {
  const response = await client.get(`/v1/chat/memory/${conversationId}`);
  return response.data;
}

export async function sendChatMessageStream(
  request: ChatRequest,
  onChunk: (text: string) => void,
  onDone: () => void,
  onError: (error: Error) => void,
  signal?: AbortSignal
): Promise<void> {
  const token = localStorage.getItem('llm_platform_access_token');
  try {
    const response = await fetch('/api/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ ...request, stream: true }),
      signal,
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('No response body reader available');
    }

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
        if (!trimmed || !trimmed.startsWith('data: ')) continue;
        const data = trimmed.slice(6);
        if (data === '[DONE]') {
          onDone();
          return;
        }
        try {
          const parsed = JSON.parse(data);
          const content = parsed.choices?.[0]?.delta?.content;
          if (content) {
            onChunk(content);
          }
        } catch {
          // Skip unparseable chunks
        }
      }
    }
    onDone();
  } catch (error: any) {
    if (error.name === 'AbortError') {
      onDone();
      return;
    }
    onError(error);
  }
}
