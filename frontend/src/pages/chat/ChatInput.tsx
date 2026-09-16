import { useState, useCallback, KeyboardEvent, useEffect, useRef } from 'react';
import { Input, Select, Button, Space, Tag, message as antdMessage, Tooltip, Popover } from 'antd';
import { SendOutlined, ClearOutlined, PaperClipOutlined, LoadingOutlined, DatabaseOutlined, LinkOutlined, ApiOutlined } from '@ant-design/icons';
import { useChatStore } from '@/store';
import { MODEL_OPTIONS, DEFAULT_MODEL } from '@/utils/constants';
import { listExperts } from '@/api/experts';
import { listSkills } from '@/api/skills';
import { listKnowledgeBases } from '@/api/rag';
import { listMCPServers } from '@/api/mcp';
import { parseDocument, ocrImage } from '@/api/files';

const { TextArea } = Input;

export interface SendOptions {
  content: string;
  model: string;
  expertName?: string;
  ragKbs?: string[];
  mcpServers?: string[];
}

interface ChatInputProps {
  onSend: (opts: SendOptions) => Promise<void>;
}

interface Attachment {
  name: string;
  kind: 'image' | 'document';
  content: string; // 解析后的文本
  previewUrl?: string; // 图片预览地址
  loading: boolean;
}

export function ChatInput({ onSend }: ChatInputProps) {
  const [message, setMessage] = useState('');
  const [model, setModel] = useState(DEFAULT_MODEL);
  const [expert, setExpert] = useState<string | undefined>(undefined);
  const [experts, setExperts] = useState<any[]>([]);
  const [skills, setSkills] = useState<any[]>([]);
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<{ name: string; documents: number }[]>([]);
  const [selectedKbs, setSelectedKbs] = useState<string[]>([]);
  const [mcpServers, setMcpServers] = useState<string[]>([]);
  const [selectedMcps, setSelectedMcps] = useState<string[]>([]);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [isSending, setIsSending] = useState(false);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    listExperts().then(r => setExperts(r.items || [])).catch(() => {});
    listSkills().then(r => setSkills(r.items || [])).catch(() => {});
    listKnowledgeBases().then(r => setKnowledgeBases(r.items || [])).catch(() => {});
    listMCPServers().then(r => setMcpServers((Array.isArray(r) ? r : []).map((s: any) => s.name))).catch(() => {});
  }, []);

  const handleFileSelect = async (file: File) => {
    const isImage = file.type.startsWith('image/');
    const kind: 'image' | 'document' = isImage ? 'image' : 'document';

    // 图片直接给预览地址；文档走解析
    const previewUrl = isImage ? URL.createObjectURL(file) : undefined;

    const temp: Attachment = { name: file.name, kind, content: '', previewUrl, loading: true };
    setAttachments(prev => [...prev, temp]);

    try {
      if (isImage) {
        const result = await ocrImage(file);
        const text = result?.ocr?.text || '';
        if (!text) {
          antdMessage.warning(`${file.name} 未识别到文字（OCR 引擎不可用），已保留图片预览`);
        }
        setAttachments(prev => prev.map(a => a.name === file.name ? { ...a, content: text, loading: false } : a));
      } else {
        const result = await parseDocument(file);
        setAttachments(prev => prev.map(a => a.name === file.name ? { ...a, content: result.text || '', loading: false } : a));
      }
    } catch (err: any) {
      antdMessage.error(`解析失败: ${err?.message || '未知错误'}`);
      setAttachments(prev => prev.filter(a => a.name !== file.name));
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    }
    return false; // prevent auto upload
  };

  const removeAttachment = (name: string) => {
    setAttachments(prev => {
      const target = prev.find(a => a.name === name);
      if (target?.previewUrl) URL.revokeObjectURL(target.previewUrl);
      return prev.filter(x => x.name !== name);
    });
  };

  const handleSend = useCallback(async () => {
    const trimmed = message.trim();
    const hasAttachment = attachments.some(a => a.content || a.previewUrl);
    if ((!trimmed && !hasAttachment) || isSending || isStreaming) return;

    // 组装可见消息：附件内容 + 用户输入（技能/知识库/MCP 由 store 注入系统上下文）
    let fullContent = '';
    if (attachments.length > 0) {
      fullContent += '【附件内容】\n';
      for (const a of attachments) {
        if (a.content) {
          fullContent += `\n[${a.name}]\n${a.content.slice(0, 3000)}\n`;
        }
      }
    }
    if (trimmed) {
      fullContent += fullContent ? `\n${trimmed}` : trimmed;
    }

    setIsSending(true);
    try {
      await onSend({
        content: fullContent || trimmed,
        model,
        expertName: expert || undefined,
        ragKbs: selectedKbs.length ? selectedKbs : undefined,
        mcpServers: selectedMcps.length ? selectedMcps : undefined,
      });
      setMessage('');
      setAttachments(prev => {
        prev.forEach(a => { if (a.previewUrl) URL.revokeObjectURL(a.previewUrl); });
        return [];
      });
      setSelectedSkills([]);
      setSelectedKbs([]);
      setSelectedMcps([]);
    } catch {
      // Error handled by store
    } finally {
      setIsSending(false);
    }
  }, [message, model, expert, selectedSkills, selectedKbs, selectedMcps, attachments, isSending, isStreaming, onSend]);

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
    setAttachments(prev => {
      prev.forEach(a => { if (a.previewUrl) URL.revokeObjectURL(a.previewUrl); });
      return [];
    });
  }, []);

  const isLoading = isSending || isStreaming;

  const kbOptions = knowledgeBases.map(k => ({ value: k.name, label: `${k.name}（${k.documents} 篇）` }));
  const mcpOptions = mcpServers.map(n => ({ value: n, label: n }));

  return (
    <div className="border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-dark-900 px-4 py-3">
      {/* 选择器行：模型 + 专家 + 技能 + 知识库 + MCP */}
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
        <Select
          mode="multiple"
          value={selectedKbs}
          onChange={setSelectedKbs}
          size="small"
          className="min-w-40"
          placeholder="知识库（不选则不调用 RAG）"
          allowClear
          maxTagCount={1}
          suffixIcon={<DatabaseOutlined />}
          options={kbOptions}
          disabled={isLoading}
          notFoundContent="暂无知识库，请先到「RAG 知识库」上传文档"
        />
        <Select
          mode="multiple"
          value={selectedMcps}
          onChange={setSelectedMcps}
          size="small"
          className="min-w-40"
          placeholder="MCP 服务器"
          allowClear
          maxTagCount={1}
          suffixIcon={<LinkOutlined />}
          options={mcpOptions}
          disabled={isLoading}
          notFoundContent="暂无 MCP 服务器，请先到「MCP 管理」添加"
        />
        <Popover
          content={
            <div className="text-xs max-w-xs">
              <p>选择具体<b>知识库</b>后，对话会从该库检索真实上下文注入；不选则不调用 RAG。</p>
              <p className="mt-1">选择<b>MCP 服务器</b>后，其工具列表会随上下文告知模型（工具调用在「智能体专家」中执行）。</p>
            </div>
          }
        >
          <ApiOutlined className="text-gray-400 cursor-help" />
        </Popover>
      </div>

      {/* 附件预览 */}
      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2 items-start">
          {attachments.map((a) => (
            <div key={a.name} className="relative border border-gray-200 dark:border-gray-700 rounded-lg p-1 bg-gray-50 dark:bg-gray-800">
              {a.kind === 'image' && a.previewUrl ? (
                <Tooltip title={a.name}>
                  <img src={a.previewUrl} alt={a.name} className="h-16 w-16 object-cover rounded" />
                </Tooltip>
              ) : (
                <Tag
                  closable
                  onClose={() => removeAttachment(a.name)}
                  icon={a.loading ? <LoadingOutlined /> : undefined}
                  color={a.kind === 'image' ? 'purple' : 'blue'}
                  style={{ marginRight: 0 }}
                >
                  {a.name}{a.content ? ' ✓' : ''}
                </Tag>
              )}
              {a.kind === 'image' && a.previewUrl && (
                <button
                  onClick={() => removeAttachment(a.name)}
                  className="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-red-500 text-white text-xs leading-5"
                  title="移除"
                >×</button>
              )}
            </div>
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
          title="上传文件/图片（图片显示预览并自动 OCR，文档自动解析）"
        />
        <TextArea
          id="chat-message-input"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入消息... (Ctrl+Enter 发送)，可上传文件/图片，选择知识库与 MCP"
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
            disabled={(!message.trim() && !attachments.some(a => a.content || a.previewUrl)) || isLoading}
            style={{ background: 'linear-gradient(135deg, #1677ff, #722ed1)', border: 'none' }}
          >
            {!isLoading && '发送'}
          </Button>
        </Space.Compact>
      </div>
    </div>
  );
}
