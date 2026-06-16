import { useState, useCallback, KeyboardEvent } from 'react';
import { Input, Select, Button, Space } from 'antd';
import { SendOutlined, ClearOutlined } from '@ant-design/icons';
import { useChatStore } from '@/store';
import { MODEL_OPTIONS, DEFAULT_MODEL } from '@/utils/constants';

const { TextArea } = Input;

interface ChatInputProps {
  onSend: (content: string, model: string) => Promise<void>;
}

export function ChatInput({ onSend }: ChatInputProps) {
  const [message, setMessage] = useState('');
  const [model, setModel] = useState(DEFAULT_MODEL);
  const [isSending, setIsSending] = useState(false);
  const isStreaming = useChatStore((s) => s.isStreaming);

  const handleSend = useCallback(async () => {
    const trimmed = message.trim();
    if (!trimmed || isSending || isStreaming) return;

    setIsSending(true);
    try {
      await onSend(trimmed, model);
      setMessage('');
    } catch {
      // Error handled by store
    } finally {
      setIsSending(false);
    }
  }, [message, model, isSending, isStreaming, onSend]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  const handleClear = useCallback(() => {
    setMessage('');
  }, []);

  const isLoading = isSending || isStreaming;

  return (
    <div className="border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-dark-900 px-4 py-3">
      {/* Model selector row */}
      <div className="flex items-center gap-2 mb-2">
        <Select
          value={model}
          onChange={setModel}
          size="small"
          className="w-48"
          options={MODEL_OPTIONS.map((m) => ({
            value: m.value,
            label: (
              <div className="flex items-center gap-2">
                <span>{m.label}</span>
                <span className="text-xs text-gray-400">{m.provider}</span>
              </div>
            ),
          }))}
          disabled={isLoading}
          showSearch
          filterOption={(input, option) =>
            (option?.label as string)?.toLowerCase().includes(input.toLowerCase()) ||
            (option?.value as string)?.toLowerCase().includes(input.toLowerCase())
          }
        />
        <span className="text-xs text-gray-400 hidden sm:inline">
          Ctrl+Enter 发送
        </span>
      </div>

      {/* Input row */}
      <div className="flex items-end gap-2">
        <TextArea
          id="chat-message-input"
          name="message"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入消息... (Ctrl+Enter 发送)"
          autoSize={{ minRows: 1, maxRows: 6 }}
          disabled={isLoading}
          className="!rounded-xl flex-1"
          style={{ resize: 'none' }}
        />
        <Space.Compact>
          {message.trim() && (
            <Button
              icon={<ClearOutlined />}
              onClick={handleClear}
              disabled={isLoading}
              className="!rounded-l-xl !rounded-r-none"
              title="清空输入"
            />
          )}
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            loading={isLoading}
            disabled={!message.trim() || isLoading}
            className={message.trim() ? '!rounded-l-none !rounded-r-xl' : '!rounded-xl'}
            style={{
              background: message.trim()
                ? 'linear-gradient(135deg, #1677ff, #722ed1)'
                : undefined,
              border: message.trim() ? 'none' : undefined,
            }}
          >
            {!isLoading && '发送'}
          </Button>
        </Space.Compact>
      </div>
    </div>
  );
}
