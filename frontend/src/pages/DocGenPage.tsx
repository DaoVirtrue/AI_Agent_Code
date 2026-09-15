import { useEffect, useState } from 'react';
import { Card, Input, Select, Button, Typography, Space, Tag, message } from 'antd';
import { FileTextOutlined, DownloadOutlined, FileMarkdownOutlined, FileWordOutlined, FileExcelOutlined, FilePptOutlined } from '@ant-design/icons';
import { useAppStore } from '@/store';
import { listDocFormats, generateDocument, downloadBlob } from '@/api/documents';

const { TextArea } = Input;
const { Title, Text } = Typography;

const FORMAT_ICONS: Record<string, any> = {
  md: <FileMarkdownOutlined />,
  docx: <FileWordOutlined />,
  xlsx: <FileExcelOutlined />,
  pptx: <FilePptOutlined />,
};

export function DocGenPage() {
  const setBreadcrumbs = useAppStore((s) => s.setBreadcrumbs);
  const [topic, setTopic] = useState('');
  const [format, setFormat] = useState('md');
  const [title, setTitle] = useState('');
  const [generating, setGenerating] = useState(false);
  const [formats, setFormats] = useState<string[]>(['md', 'docx', 'xlsx', 'pptx']);

  useEffect(() => {
    setBreadcrumbs([{ title: '文档生成' }]);
    listDocFormats().then((r) => setFormats(r.formats)).catch(() => {});
  }, [setBreadcrumbs]);

  const handleGenerate = async () => {
    if (!topic.trim()) return;
    setGenerating(true);
    try {
      const blob = await generateDocument(topic, format, title || topic.slice(0, 20));
      const ext = format;
      downloadBlob(blob, `${title || topic.slice(0, 20)}.${ext}`);
      message.success('文档已生成并开始下载');
    } catch (err: any) {
      message.error('生成失败: ' + (err?.message || '未知错误'));
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="space-y-4 animate-fade-in">
      <Title level={4} className="!mb-0">文档生成</Title>

      <Card title={<span className="flex items-center gap-2"><FileTextOutlined /> 生成配置</span>}>
        <Space direction="vertical" className="w-full" size="middle">
          <div>
            <Text strong className="block mb-2">文档主题</Text>
            <TextArea
              rows={3}
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="输入文档主题，例如：'2025 年人工智能行业报告'"
            />
          </div>
          <div>
            <Text strong className="block mb-2">输出格式</Text>
            <Select value={format} onChange={setFormat} className="w-full">
              {formats.map((f) => (
                <Select.Option key={f} value={f}>
                  {FORMAT_ICONS[f]} {f.toUpperCase()}
                </Select.Option>
              ))}
            </Select>
          </div>
          <div>
            <Text strong className="block mb-2">文件名（可选）</Text>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="默认用主题作文件名" />
          </div>
          <Button
            type="primary"
            icon={<DownloadOutlined />}
            onClick={handleGenerate}
            loading={generating}
            disabled={!topic.trim()}
            style={{ background: 'linear-gradient(135deg, #1677ff, #722ed1)', border: 'none' }}
          >
            生成并下载
          </Button>
        </Space>
      </Card>

      <Card title="支持格式">
        <Space wrap>
          {formats.map((f) => (
            <Tag key={f} icon={FORMAT_ICONS[f]} color="blue">{f.toUpperCase()}</Tag>
          ))}
        </Space>
        <Text type="secondary" className="block mt-3">
          内容由 DeepSeek 生成，转为对应格式后浏览器直接下载。Markdown 始终可用，docx/xlsx/pptx 依赖对应库（已内置）。
        </Text>
      </Card>
    </div>
  );
}
