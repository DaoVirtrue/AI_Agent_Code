import { useEffect, useState } from 'react';
import { Card, Input, Select, Button, Typography, Space, Tag, message, Tabs, Upload, Switch, Alert } from 'antd';
import { FileTextOutlined, DownloadOutlined, FileMarkdownOutlined, FileWordOutlined, FileExcelOutlined, FilePptOutlined, PictureOutlined, InboxOutlined } from '@ant-design/icons';
import { useAppStore } from '@/store';
import { listDocFormats, generateDocument, downloadBlob, ocrImage } from '@/api/documents';

const { TextArea } = Input;
const { Title, Text, Paragraph } = Typography;
const { Dragger } = Upload;

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

  // OCR state
  const [ocrResult, setOcrResult] = useState<any>(null);
  const [ocrLoading, setOcrLoading] = useState(false);
  const [genAnswer, setGenAnswer] = useState(true);
  const [ocrQuestion, setOcrQuestion] = useState('');

  useEffect(() => {
    setBreadcrumbs([{ title: '文档工具' }]);
    listDocFormats().then((r) => setFormats(r.formats)).catch(() => {});
  }, [setBreadcrumbs]);

  const handleGenerate = async () => {
    if (!topic.trim()) return;
    setGenerating(true);
    try {
      const blob = await generateDocument(topic, format, title || topic.slice(0, 20));
      downloadBlob(blob, `${title || topic.slice(0, 20)}.${format}`);
      message.success('文档已生成并开始下载');
    } catch (err: any) {
      message.error('生成失败: ' + (err?.message || '未知错误'));
    } finally {
      setGenerating(false);
    }
  };

  const handleOcr = async (file: File) => {
    setOcrLoading(true);
    setOcrResult(null);
    try {
      const result = await ocrImage(file, genAnswer, ocrQuestion || undefined);
      setOcrResult(result);
      if (result.ocr?.text) {
        message.success(`OCR 识别完成（引擎: ${result.ocr.engine}）`);
      } else {
        message.warning('OCR 引擎不可用（未安装 tesseract），已提取图片信息');
      }
    } catch (err: any) {
      message.error('识别失败: ' + (err?.message || '未知错误'));
    } finally {
      setOcrLoading(false);
    }
    return false;
  };

  const genTab = (
    <div className="space-y-4">
      <Card title={<span className="flex items-center gap-2"><FileTextOutlined /> 生成配置</span>}>
        <Space direction="vertical" className="w-full" size="middle">
          <div>
            <Text strong className="block mb-2">文档主题</Text>
            <TextArea rows={3} value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="输入文档主题，例如：'2025 年人工智能行业报告'" />
          </div>
          <div>
            <Text strong className="block mb-2">输出格式</Text>
            <Select value={format} onChange={setFormat} className="w-full">
              {formats.map((f) => (
                <Select.Option key={f} value={f}>{FORMAT_ICONS[f]} {f.toUpperCase()}</Select.Option>
              ))}
            </Select>
          </div>
          <div>
            <Text strong className="block mb-2">文件名（可选）</Text>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="默认用主题作文件名" />
          </div>
          <Button type="primary" icon={<DownloadOutlined />} onClick={handleGenerate} loading={generating} disabled={!topic.trim()}
            style={{ background: 'linear-gradient(135deg, #1677ff, #722ed1)', border: 'none' }}>
            生成并下载
          </Button>
        </Space>
      </Card>
    </div>
  );

  const ocrTab = (
    <div className="space-y-4">
      <Alert type="info" showIcon message="OCR 说明" description="上传图片后，系统提取图片文字（需安装 tesseract OCR 引擎），并可基于识别文字生成答案或文档。识别文字会索引进 RAG 知识库，支持后续检索。" />
      <Space>
        <Text strong>识别后生成答案</Text>
        <Switch checked={genAnswer} onChange={setGenAnswer} />
        {genAnswer && <Input placeholder="提问（留空则自动总结）" value={ocrQuestion} onChange={(e) => setOcrQuestion(e.target.value)} className="w-64" />}
      </Space>
      <Dragger beforeUpload={handleOcr} showUploadList={false} accept="image/*" disabled={ocrLoading}>
        <p className="ant-upload-drag-icon"><InboxOutlined /></p>
        <p className="ant-upload-text">{ocrLoading ? '识别中...' : '点击或拖拽图片到此区域'}</p>
        <p className="ant-upload-hint">支持 PNG / JPG / 等图片格式</p>
      </Dragger>
      {ocrResult && (
        <Card title="识别结果">
          {ocrResult.ocr?.text ? (
            <>
              <Text strong>识别文字：</Text>
              <Paragraph className="whitespace-pre-wrap mt-2 bg-gray-50 dark:bg-gray-800 p-3 rounded">{ocrResult.ocr.text}</Paragraph>
            </>
          ) : (
            <Text type="warning">未识别到文字（OCR 引擎不可用）</Text>
          )}
          {ocrResult.image_info && (
            <div className="mt-2">
              <Text type="secondary">图片信息：{ocrResult.image_info.width}×{ocrResult.image_info.height}，{ocrResult.image_info.format}，{(ocrResult.image_info.size_bytes / 1024).toFixed(1)}KB</Text>
            </div>
          )}
          {ocrResult.answer && (
            <>
              <Text strong className="block mt-3">生成的答案：</Text>
              <Paragraph className="whitespace-pre-wrap mt-1">{ocrResult.answer}</Paragraph>
            </>
          )}
        </Card>
      )}
    </div>
  );

  return (
    <div className="space-y-4 animate-fade-in">
      <Title level={4} className="!mb-0">文档工具</Title>
      <Tabs
        defaultActiveKey="gen"
        items={[
          { key: 'gen', label: <span><FileTextOutlined /> 文档生成</span>, children: genTab },
          { key: 'ocr', label: <span><PictureOutlined /> 图片识别</span>, children: ocrTab },
        ]}
      />
    </div>
  );
}
