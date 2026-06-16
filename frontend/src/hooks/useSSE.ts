import { useRef, useState, useCallback, useEffect } from 'react';
import { getToken } from '@/utils/token';
import { API_BASE_URL } from '@/utils/constants';

interface UseSSEOptions {
  onChunk?: (data: unknown) => void;
  onDone?: () => void;
  onError?: (error: Error) => void;
}

interface UseSSEReturn {
  isStreaming: boolean;
  startStream: (url: string, body?: Record<string, unknown>) => void;
  abortStream: () => void;
}

export function useSSE(options: UseSSEOptions = {}): UseSSEReturn {
  const { onChunk, onDone, onError } = options;
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const readerRef = useRef<ReadableStreamDefaultReader<Uint8Array> | null>(null);

  const cleanup = useCallback(() => {
    if (readerRef.current) {
      readerRef.current.cancel().catch(() => {});
      readerRef.current = null;
    }
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
  }, []);

  useEffect(() => {
    return cleanup;
  }, [cleanup]);

  const startStream = useCallback(
    async (url: string, body?: Record<string, unknown>) => {
      cleanup();
      setIsStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      const token = getToken();

      try {
        const fullUrl = url.startsWith('http') ? url : `${API_BASE_URL}${url}`;
        const response = await fetch(fullUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: body ? JSON.stringify(body) : undefined,
          signal: controller.signal,
        });

        if (!response.ok) {
          const errorText = await response.text().catch(() => 'Unknown error');
          throw new Error(`HTTP ${response.status}: ${errorText}`);
        }

        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error('No response body reader available');
        }
        readerRef.current = reader;

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            setIsStreaming(false);
            onDone?.();
            return;
          }

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || !trimmed.startsWith('data: ')) continue;

            const data = trimmed.slice(6);
            if (data === '[DONE]') {
              setIsStreaming(false);
              onDone?.();
              return;
            }

            try {
              const parsed = JSON.parse(data);
              onChunk?.(parsed);
            } catch {
              // Skip malformed chunks
            }
          }
        }
      } catch (err: any) {
        if (err.name === 'AbortError') {
          setIsStreaming(false);
          onDone?.();
          return;
        }
        setIsStreaming(false);
        onError?.(err instanceof Error ? err : new Error(err?.message || 'SSE stream error'));
      }
    },
    [onChunk, onDone, onError, cleanup]
  );

  const abortStream = useCallback(() => {
    cleanup();
    setIsStreaming(false);
  }, [cleanup]);

  return { isStreaming, startStream, abortStream };
}
