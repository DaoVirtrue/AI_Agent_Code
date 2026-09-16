import { useState, useCallback, KeyboardEvent, useEffect, useRef } from 'react';
import { Input, Select, Button, Space, Upload, Tag, message } from 'antd';
import { SendOutlined, ClearOutlined, PaperClipOutlined, LoadingOutlined } from '@ant-design/icons';
import { useChatStore } from '@/store';
import { MODEL_OPTIONS, DEFAULT_MODEL } from '@/utils/constants';
import { listExperts } from '@/api/experts';
import { listSkills } from '@/api/skills';
import { parseDocument, ocrImage } from '@/api/files';

const { TextArea } = Input;

interface ChatInputProps {
  onSend: (content: string, model: string, expertName?: string) => Promise<void>;
}

interface Attachment {
  name: string;
  kind: 'image' | 'document';
  content: string; // 解析后的文本
  loading: boolean;
}

export function ChatInput({ onSend }: ChatInputProps) {
  const [message, setMessage] = useState('');
  const [model, setModel] = useState(DEFAULT_MODEL);
  const [expert, setExpert] = useState<string | undefined>(undefined);
  const [experts, setExperts] = useState<any[]>([]);
  const [skills, setSkills] = useState<any[]>([]);
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
  const [useRag, setUseRag] = useState(false);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [isSending, setIsSending] = useState(false);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    listExperts().then(r => setExperts(r.items || [])).catch(() => {});
    listSkills().then(r => setSkills(r.items || [])).catch(() => {});
  }, []);

  const handleFileSelect = async (file: File) => {
    const isImage = file.type.startsWith('image/');
    const kind: 'image' | 'document' = isImage ? 'image' : 'document';

    // 先加入附件列表（loading 态）
    const temp: Attachment = { name: file.name, kind, content: '', loading: true };
    setAttachments(prev => [...prev, temp]);

    try {
      if (isImage) {
        const result = await ocrImage(file);
        const text = result?.ocr?.text || '';
        if (!text) {
          message.warning(`${file.name} 未识别到文字（OCR 引擎不可用）`);
        }
        setAttachments(prev => prev.map(a => a.name === file.name ? { ...a, content: text, loading: false } : a));
      } else {
        const result = await parseDocument(file);
        setAttachments(prev => prev.map(a => a.name === file.name ? { ...a, content: result.text || '', loading: false } : a));
      }
    } catch (err: any) {
      message.error(`解析失败: ${err?.message || '未知错误'}`);
      setAttachments(prev => prev.filter(a => a.name !== file.name));
    }
    return false; // prevent auto upload
  };

  const handleSend = useCallback(async () => {
    const trimmed = message.trim();
    const hasAttachment = attachments.some(a => a.content);
    if ((!trimmed && !hasAttachment) || isSending || isStreaming) return;

    // 组装消息：附件解析内容 + 技能指令 + RAG 提示 + 用户输入
    let fullContent = '';
    if (attachments.length > 0) {
      fullContent += '【附件内容】\n';
      for (const a of attachments) {
        if (a.content) {
          fullContent += `\n[${a.name}]\n${a.content.slice(0, 3000)}\n`;
        }
      }
    }
    if (selectedSkills.length > 0) {
      fullContent += `\n【启用的技能】${selectedSkills.join('、')}\n`;
    }
    if (useRag) {
      fullContent += `\n【知识库检索】请结合知识库内容回答\n`;
    }
    if (trimmed) {
      fullContent += `\n${trimmed}`;
    }

    setIsSending(true);
    try {
      await onSend(fullContent || trimmed, model, expert);
      setMessage('');
      setAttachments([]);
    } catch {
      // Error handled by store
    } finally {
      setIsSending(false);
    }
  }, [message, model, expert, selectedSkills, useRag, attachments, isSending, isStreaming, onSend]);

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
    setAttachments([]);
  }, []);

  const isLoading = isSending || isStreaming;

  return (
    <div className="border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-dark-900 px-4 py-3">
      {/* 选择器行：模型 + 专家 + 技能 + RAG */}
      <div className="flex items-center gap-2 mb-2 flex-wrap">
        <Select
          value={model}
          onChange={setModel}
          size="small"
          className="w-40"
          options={MODEL_OPTIONS.map((m) => ({ value: m.value, label: m.label }))}
          disabled={isLoading}
        />
        <Select
          value={expert}
          onChange={setExpert}
          size="small"
          className="w-36"
          placeholder="选择专家"
          allowClear
          options={[
            { value: '', label: '通用助手' },
            ...experts.map((e: any) => ({ value: e.name, label: e.name })),
          ]}
          disabled={isLoading}
        />
        <Select
          mode="multiple"
          value={selectedSkills}
          onChange={setSelectedSkills}
          size="small"
          className="min-w-32"
          placeholder="技能"
          maxTagCount={1}
          options={skills.map((s: any) => ({ value: s.name, label: s.name }))}
          disabled={isLoading}
        />
        <Tag
          color={useRag ? 'green' : 'default'}
          style={{ cursor: 'pointer', marginRight: 0 }}
          onClick={() => setUseRag(!useRag)}
        >
          {useRag ? 'RAG 开' : 'RAG 关'}
        </Tag>
      </div>

      {/* 附件预览 */}
      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {attachments.map((a) => (
            <Tag
              key={a.name}
              closable
              onClose={() => setAttachments(prev => prev.filter(x => x.name !== a.name))}
              icon={a.loading ? <LoadingOutlined /> : undefined}
              color={a.kind === 'image' ? 'purple' : 'blue'}
            >
              {a.name}{a.content ? ' ✓' : ''}
            </Tag>
          ))}
        </div>
      )}

      {/* 输入行 */}
      <div className="flex items-end gap-2">
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*,.pdf,.docx,.doc,.txt,.md,.csv,.json"
          multiple
          style={{ display: 'none' }}
          onChange={(e) => { Array.from(e.target.files || []).forEach(f => handleFileSelect(f)); e.target.value = ''; }}
        />
        <Button
          icon={<PaperClipOutlined />}
          onClick={() => fileInputRef.current?.click()}
          disabled={isLoading}
          title="上传文件/图片（图片自动 OCR，文档自动解析）"
        />
        <TextArea
          id="chat-message-input"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入消息... (Ctrl+Enter 发送)，可上传文件/图片"
          autoSize={{ minRows: 1, maxRows: 6 }}
          disabled={isLoading}
          className="!rounded-xl flex-1"
          style={{ resize: 'none' }}
        />
        <Space.Compact>
          {message.trim() && (
            <Button icon={<ClearOutlined />} onClick={handleClear} disabled={isLoading} title="清空" />
          )}
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            loading={isLoading}
            disabled={(!message.trim() && !attachments.some(a => a.content)) || isLoading}
            style={{ background: 'linear-gradient(135deg, #1677ff, #722ed1)', border: 'none' }}
          >
            {!isLoading && '发送'}
          </Button>
        </Space.Compact>
      </div>
    </div>
  );
}
