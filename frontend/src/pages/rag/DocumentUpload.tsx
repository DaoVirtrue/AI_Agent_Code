import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Upload,
  Button,
  Progress,
  Spin,
  InputNumber,
  Card,
  Typography,
  Space,
  Divider,
  Tag,
  message,
  Row,
  Col,
} from 'antd';
import {
  InboxOutlined,
  FileTextOutlined,
  DeleteOutlined,
  CloudUploadOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useRAGStore } from '@/store/ragStore';
import { formatBytes } from '@/utils/format';
import type { UploadFile } from 'antd/es/upload/interface';

const { Dragger } = Upload;
const { Text, Title } = Typography;

const ACCEPTED_FILE_TYPES = '.pdf,.docx,.md,.txt';

const fileTypeColorMap: Record<string, string> = {
  pdf: 'red',
  docx: 'blue',
  md: 'green',
  txt: 'default',
};

export default function DocumentUpload() {
  const { uploadDoc, uploadProgress, isUploading, error, clearError } = useRAGStore();

  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [chunkSize, setChunkSize] = useState<number>(1024);
  const [chunkOverlap, setChunkOverlap] = useState<number>(128);
  const [uploadCompleted, setUploadCompleted] = useState<boolean>(false);

  const prevProgressRef = useRef<number>(0);
  const prevUploadingRef = useRef<boolean>(false);

  // Detect upload completion: progress hits 100 and isUploading transitions to false
  useEffect(() => {
    const wasUploading = prevUploadingRef.current;
    const wasProgress = prevProgressRef.current;
    const nowProgress = uploadProgress;
    const nowUploading = isUploading;

    if (wasUploading && !nowUploading && wasProgress === 100 && nowProgress === 100) {
      message.success('文档上传成功！');
      setUploadCompleted(true);
    }

    prevProgressRef.current = nowProgress;
    prevUploadingRef.current = nowUploading;
  }, [uploadProgress, isUploading]);

  // Show error if one occurs
  useEffect(() => {
    if (error) {
      message.error(error);
      clearError();
    }
  }, [error, clearError]);

  const selectedFile = fileList.length > 0 ? fileList[0] : null;
  const fileExtension = selectedFile?.name
    ? selectedFile.name.split('.').pop()?.toLowerCase() || 'unknown'
    : 'unknown';

  const handleBeforeUpload = useCallback((file: UploadFile) => {
    setFileList([file]);
    setUploadCompleted(false);
    return false; // Prevent auto-upload
  }, []);

  const handleRemoveFile = useCallback(() => {
    setFileList([]);
    setUploadCompleted(false);
  }, []);

  const handleUpload = useCallback(async () => {
    if (!selectedFile?.originFileObj) {
      message.warning('请先选择文件。');
      return;
    }

    setUploadCompleted(false);
    try {
      await uploadDoc(selectedFile.originFileObj as File);
    } catch {
      // Error is handled by the store and caught in the useEffect
    }
  }, [selectedFile, uploadDoc]);

  const handleReset = useCallback(() => {
    setFileList([]);
    setUploadCompleted(false);
    setChunkSize(1024);
    setChunkOverlap(128);
  }, []);

  const isUploadInProgress = isUploading;

  return (
    <div className="p-4 space-y-6">
      {/* Upload Area */}
      <Spin spinning={isUploadInProgress} tip="正在上传文档...">
        <Card className="!rounded-xl" bordered={false}>
          <Dragger
            accept={ACCEPTED_FILE_TYPES}
            maxCount={1}
            fileList={fileList}
            beforeUpload={handleBeforeUpload}
            onRemove={handleRemoveFile}
            disabled={isUploadInProgress}
            showUploadList={false}
            className="!rounded-lg"
          >
            <p className="ant-upload-drag-icon">
              <InboxOutlined style={{ fontSize: 48, color: '#1677ff' }} />
            </p>
            <p className="ant-upload-text text-base font-medium">
              点击或拖拽文件到此区域上传
            </p>
            <p className="ant-upload-hint text-gray-400">
              支持格式：PDF、DOCX、Markdown、TXT（每次仅限 1 个文件）
            </p>
          </Dragger>
        </Card>
      </Spin>

      {/* Selected File Info */}
      {selectedFile && (
        <Card className="!rounded-xl" size="small">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <FileTextOutlined style={{ fontSize: 32, color: '#1677ff' }} />
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <Text strong className="text-lg">
                    {selectedFile.name}
                  </Text>
                  <Tag color={fileTypeColorMap[fileExtension] || 'default'}>
                    {fileExtension.toUpperCase()}
                  </Tag>
                </div>
                <Space size="large" className="mt-1">
                  <Text type="secondary">
                    大小: {selectedFile.size ? formatBytes(selectedFile.size) : 'N/A'}
                  </Text>
                  <Text type="secondary">
                    类型: {selectedFile.type || '未知'}
                  </Text>
                </Space>
              </div>
            </div>
            <Button
              danger
              icon={<DeleteOutlined />}
              onClick={handleRemoveFile}
              disabled={isUploadInProgress}
              size="small"
            >
              移除
            </Button>
          </div>

          {isUploadInProgress && (
            <div className="mt-4">
              <Progress
                percent={Math.round(uploadProgress)}
                status={uploadProgress >= 100 ? 'success' : 'active'}
                strokeColor={{ from: '#108ee9', to: '#87d068' }}
              />
              <Text type="secondary" className="text-sm">
                {uploadProgress >= 100 ? '处理中...' : `上传中: ${Math.round(uploadProgress)}%`}
              </Text>
            </div>
          )}

          {uploadCompleted && !isUploadInProgress && (
            <div className="mt-4">
              <Progress percent={100} status="success" />
              <Text type="success" className="text-sm">
                上传完成！文档正在被索引。
              </Text>
            </div>
          )}
        </Card>
      )}

      {/* Upload Button */}
      {selectedFile && !uploadCompleted && (
        <div className="flex gap-3">
          <Button
            type="primary"
            icon={<CloudUploadOutlined />}
            onClick={handleUpload}
            loading={isUploadInProgress}
            size="large"
            className="!rounded-lg"
            disabled={isUploadInProgress}
          >
            {isUploadInProgress ? '上传中...' : '上传'}
          </Button>
          <Button
            icon={<ReloadOutlined />}
            onClick={handleReset}
            disabled={isUploadInProgress}
            size="large"
            className="!rounded-lg"
          >
            重置
          </Button>
        </div>
      )}

      <Divider />

      {/* Chunk Configuration */}
      <Card
        title={
          <span className="font-medium">分块配置</span>
        }
        className="!rounded-xl"
        size="small"
      >
        <Text type="secondary" className="block mb-4">
          配置文档如何分割为块以进行索引。这些设置将作为元数据应用。
        </Text>
        <Row gutter={[24, 16]}>
          <Col xs={24} sm={12} md={8}>
            <div className="space-y-2">
              <Text strong className="block text-sm">
                分块大小
              </Text>
              <InputNumber
                min={256}
                max={4096}
                step={256}
                value={chunkSize}
                onChange={(value) => setChunkSize(value || 1024)}
                className="w-full"
                addonAfter="tokens"
                size="middle"
              />
              <Text type="secondary" className="text-xs block">
                每个分块的 Token 数（256-4096）
              </Text>
            </div>
          </Col>
          <Col xs={24} sm={12} md={8}>
            <div className="space-y-2">
              <Text strong className="block text-sm">
                重叠大小
              </Text>
              <InputNumber
                min={0}
                max={512}
                step={64}
                value={chunkOverlap}
                onChange={(value) => setChunkOverlap(value || 128)}
                className="w-full"
                addonAfter="tokens"
                size="middle"
              />
              <Text type="secondary" className="text-xs block">
                相邻分块之间的重叠大小（0-512）
              </Text>
            </div>
          </Col>
        </Row>
      </Card>
    </div>
  );
}
