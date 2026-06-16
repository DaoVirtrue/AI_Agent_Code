import {
  Table, Button, Modal, Form, Input, Select, Tag, Space,
  Popconfirm, Typography, Alert, Empty, Spin, message, InputNumber, DatePicker,
} from 'antd';
import {
  PlusOutlined, DeleteOutlined, CopyOutlined,
  EyeOutlined, EyeInvisibleOutlined, KeyOutlined, ReloadOutlined,
} from '@ant-design/icons';
import { useEffect, useState, useCallback, useMemo } from 'react';
import { useAdminStore } from '@/store/adminStore';
import { formatDate, formatDateRelative } from '@/utils/format';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';

const { Text } = Typography;
const { Option } = Select;

interface APIKeyRecord {
  id: string;
  name: string;
  keyPrefix: string;
  scopes: string[];
  rateLimit: number;
  expiresAt: string | null;
  lastUsedAt: string | null;
  isActive: boolean;
}

interface KeyFormValues {
  name: string;
  scopes: string[];
  rateLimit: number;
  expiresAt: dayjs.Dayjs | null;
}

const maskKey = (prefix: string): string => {
  if (!prefix) return '••••••••••••';
  if (prefix.length <= 8) return prefix + '••••';
  return prefix.slice(0, 8) + '••••' + prefix.slice(-4);
};

const APIKeyManager = () => {
  const {
    apiKeys, apiKeysLoading, newKeyPlain, error,
    fetchApiKeys, generateApiKey, revokeApiKeyAction, enableApiKeyAction, deleteApiKeyAction, clearNewKey, clearError,
  } = useAdminStore();

  const [modalOpen, setModalOpen] = useState(false);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [visibleKeys, setVisibleKeys] = useState<Set<string>>(new Set());
  const [copiedKey, setCopiedKey] = useState(false);
  const [form] = Form.useForm<KeyFormValues>();

  const loadKeys = useCallback(() => {
    fetchApiKeys();
  }, [fetchApiKeys]);

  useEffect(() => {
    loadKeys();
  }, [loadKeys]);

  useEffect(() => {
    if (error) {
      message.error(error);
      clearError();
    }
  }, [error, clearError]);

  // Show success modal when a new key is generated
  useEffect(() => {
    if (newKeyPlain) {
      setModalOpen(true);
    }
  }, [newKeyPlain]);

  const openCreateModal = () => {
    setModalOpen(true);
    clearNewKey();
    setCopiedKey(false);
    // Defer form reset until modal renders (Ant Design requirement)
    setTimeout(() => {
      form.resetFields();
      form.setFieldsValue({
        name: '',
        scopes: ['read'],
        rateLimit: 50,
        expiresAt: null,
      });
    }, 50);
  };

  const handleCloseModal = () => {
    setModalOpen(false);
    clearNewKey();
    setCopiedKey(false);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setConfirmLoading(true);

      await generateApiKey(values.name);
    } catch (err: any) {
      if (err?.errorFields) {
        return;
      }
      message.error(err?.message || '生成 API 密钥失败。');
    } finally {
      setConfirmLoading(false);
    }
  };

  const handleRevoke = async (keyId: string) => {
    try {
      await revokeApiKeyAction(keyId);
      message.success('API 密钥已撤销。');
    } catch (err: any) {
      message.error(err?.message || '撤销 API 密钥失败。');
    }
  };

  const handleCopyKey = async () => {
    if (newKeyPlain) {
      try {
        await navigator.clipboard.writeText(newKeyPlain);
        setCopiedKey(true);
        message.success('API 密钥已复制到剪贴板。');
      } catch {
        // Fallback for older browsers
        const textarea = document.createElement('textarea');
        textarea.value = newKeyPlain;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        setCopiedKey(true);
        message.success('API 密钥已复制到剪贴板。');
      }
    }
  };

  const toggleKeyVisibility = (keyId: string) => {
    setVisibleKeys((prev) => {
      const next = new Set(prev);
      if (next.has(keyId)) {
        next.delete(keyId);
      } else {
        next.add(keyId);
      }
      return next;
    });
  };

  const isExpiringSoon = (expiresAt: string | null): boolean => {
    if (!expiresAt) return false;
    const expiryDate = new Date(expiresAt);
    const now = new Date();
    const diffDays = (expiryDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24);
    return diffDays > 0 && diffDays <= 7;
  };

  const isExpired = (expiresAt: string | null): boolean => {
    if (!expiresAt) return false;
    return new Date(expiresAt) < new Date();
  };

  const columns: ColumnsType<APIKeyRecord> = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 160,
      render: (name: string) => <Text strong>{name}</Text>,
    },
    {
      title: '密钥前缀',
      dataIndex: 'keyPrefix',
      key: 'keyPrefix',
      width: 200,
      render: (prefix: string, record: APIKeyRecord) => {
        const isVisible = visibleKeys.has(record.id);
        return (
          <Space size="small">
            <Text code>{isVisible ? prefix || '••••••••••••' : maskKey(prefix)}</Text>
            <Button
              type="text"
              size="small"
              icon={isVisible ? <EyeInvisibleOutlined /> : <EyeOutlined />}
              onClick={() => toggleKeyVisibility(record.id)}
              title={isVisible ? '隐藏密钥' : '显示密钥'}
            />
          </Space>
        );
      },
    },
    {
      title: '权限',
      dataIndex: 'scopes',
      key: 'scopes',
      width: 200,
      render: (scopes: string[]) => (
        <Space size={[4, 4]} wrap>
          {scopes.map((scope) => {
            let color = 'default';
            if (scope === 'admin') color = 'red';
            else if (scope === 'write') color = 'orange';
            else if (scope === 'read') color = 'blue';
            return (
              <Tag key={scope} color={color}>
                {scope}
              </Tag>
            );
          })}
        </Space>
      ),
    },
    {
      title: '限流',
      dataIndex: 'rateLimit',
      key: 'rateLimit',
      width: 140,
      render: (rpm: number) => (
        <Text>{rpm !== undefined && rpm !== null ? rpm : '—'}</Text>
      ),
    },
    {
      title: '过期时间',
      dataIndex: 'expiresAt',
      key: 'expiresAt',
      width: 160,
      render: (expiresAt: string | null) => {
        if (!expiresAt) return <Text type="secondary">永不过期</Text>;

        const expired = isExpired(expiresAt);
        const soon = isExpiringSoon(expiresAt);

        if (expired) {
          return <Text type="danger">{formatDate(expiresAt)}</Text>;
        }
        if (soon) {
          return (
            <Text className="text-orange-500 font-medium">
              {formatDate(expiresAt)}
            </Text>
          );
        }
        return <Text>{formatDate(expiresAt)}</Text>;
      },
    },
    {
      title: '最后使用',
      dataIndex: 'lastUsedAt',
      key: 'lastUsedAt',
      width: 150,
      render: (lastUsedAt: string | null) => {
        if (!lastUsedAt) return <Text type="secondary">—</Text>;
        return (
          <Text title={formatDate(lastUsedAt)}>
            {formatDateRelative(lastUsedAt)}
          </Text>
        );
      },
    },
    {
      title: '状态',
      dataIndex: 'isActive',
      key: 'isActive',
      width: 100,
      render: (isActive: boolean) => (
        <Tag color={isActive ? 'green' : 'red'}>
          {isActive ? '活跃' : '已撤销'}
        </Tag>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      render: (_: unknown, record: APIKeyRecord) => (
        <Space size={0}>
          {record.isActive ? (
            <Popconfirm
              title="撤销 API 密钥"
              description={`确认撤销 "${record.name}"？`}
              onConfirm={() => handleRevoke(record.id)}
              okText="确认撤销"
              cancelText="取消"
              okButtonProps={{ danger: true }}
            >
              <Button type="link" size="small" danger icon={<DeleteOutlined />}>撤销</Button>
            </Popconfirm>
          ) : (
            <Button type="link" size="small" icon={<KeyOutlined />}
              onClick={() => enableApiKeyAction(record.id)}>恢复</Button>
          )}
          {!record.isActive && (
            <Popconfirm
              title="删除 API 密钥"
              description={`确认删除 "${record.name}"？不可恢复。`}
              onConfirm={() => deleteApiKeyAction(record.id)}
              okText="确认删除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
            >
              <Button type="link" size="small" danger>删除</Button>
            </Popconfirm>
          )}
        </Space>
      ),
        </Popconfirm>
      ),
    },
  ];

  return (
    <div className="pt-4">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <Text type="secondary">
          共 {apiKeys.length} 个 API 密钥
        </Text>
        <Space>
          <Button
            icon={<ReloadOutlined />}
            onClick={loadKeys}
            loading={apiKeysLoading}
          >
            刷新
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={openCreateModal}
          >
            生成新密钥
          </Button>
        </Space>
      </div>

      <Spin spinning={apiKeysLoading}>
        {apiKeys.length === 0 && !apiKeysLoading ? (
          <Empty
            description="暂无 API 密钥。"
            className="py-12"
          >
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={openCreateModal}
            >
              生成新密钥
            </Button>
          </Empty>
        ) : (
          <Table
            columns={columns}
            dataSource={apiKeys}
            rowKey="id"
            pagination={{ pageSize: 10, showSizeChanger: true }}
            scroll={{ x: 1200 }}
          />
        )}
      </Spin>

      <Modal
        title={
          newKeyPlain ? (
            <span className="flex items-center gap-2">
              <KeyOutlined className="text-green-500" />
              API 密钥已生成
            </span>
          ) : (
            <span className="flex items-center gap-2">
              <KeyOutlined />
              生成新 API 密钥
            </span>
          )
        }
        open={modalOpen}
        onCancel={handleCloseModal}
        footer={
          newKeyPlain
            ? [
                <Button key="copy" type="primary" icon={<CopyOutlined />} onClick={handleCopyKey}>
                  {copiedKey ? '已复制!' : '复制到剪贴板'}
                </Button>,
                <Button key="close" onClick={handleCloseModal}>
                  关闭
                </Button>,
              ]
            : [
                <Button key="cancel" onClick={handleCloseModal}>
                  取消
                </Button>,
                <Button
                  key="submit"
                  type="primary"
                  onClick={handleSubmit}
                  loading={confirmLoading}
                  icon={<KeyOutlined />}
                >
                  生成密钥
                </Button>,
              ]
        }
        destroyOnClose
      >
        {newKeyPlain ? (
          <div>
            <Alert
              type="success"
              message="密钥生成成功"
              description={
                <div>
                  <Paragraph className="!mb-3 !mt-1">
                    <Text strong>
                      请立即复制此密钥，您将无法再次查看！
                    </Text>
                  </Paragraph>
                  <div className="bg-gray-50 border rounded-md p-3 break-all font-mono text-sm">
                    {newKeyPlain}
                  </div>
                </div>
              }
              showIcon
            />
          </div>
        ) : (
          <Form
            form={form}
            layout="vertical"
            initialValues={{
              scopes: ['read'],
              rateLimit: 50,
              expiresAt: null,
            }}
          >
            <Form.Item
              name="name"
              label="密钥名称"
              rules={[
                { required: true, message: '请输入 API 密钥名称。' },
                { min: 2, message: '名称至少需要 2 个字符。' },
              ]}
            >
              <Input placeholder="例如: 生产环境 API Key" />
            </Form.Item>

            <Form.Item
              name="scopes"
              label="权限范围"
              rules={[
                { required: true, message: '请至少选择一个权限。' },
              ]}
            >
              <Select mode="multiple" placeholder="选择权限">
                <Option value="read">读取</Option>
                <Option value="write">写入</Option>
                <Option value="admin">管理</Option>
              </Select>
            </Form.Item>

            <Form.Item
              name="rateLimit"
              label="限流 (RPM)"
              rules={[
                { required: true, message: '请设置限流值。' },
              ]}
            >
              <InputNumber
                min={1}
                max={10000}
                placeholder="每分钟请求数"
                style={{ width: '100%' }}
              />
            </Form.Item>

            <Form.Item
              name="expiresAt"
              label="过期日期"
              help="留空表示永不过期。"
            >
              <DatePicker
                style={{ width: '100%' }}
                disabledDate={(current) =>
                  current ? current.isBefore(dayjs().startOf('day')) : false
                }
                placeholder="选择过期日期（可选）"
              />
            </Form.Item>
          </Form>
        )}
      </Modal>
    </div>
  );
};

export default APIKeyManager;
