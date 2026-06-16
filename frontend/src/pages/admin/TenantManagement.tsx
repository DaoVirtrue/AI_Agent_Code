import {
  Table, Button, Modal, Form, Input, Select, Switch, Space, Tag,
  Popconfirm, Typography, Empty, Spin, message,
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
} from '@ant-design/icons';
import { useEffect, useState, useCallback } from 'react';
import { useAdminStore } from '@/store/adminStore';
import { formatDate } from '@/utils/format';
import type { ColumnsType } from 'antd/es/table';

const { Text } = Typography;

interface TenantRecord {
  id: string;
  name: string;
  slug: string;
  tier: string;
  isActive: boolean;
  createdAt: string;
}

interface TenantFormValues {
  name: string;
  slug: string;
  tier: string;
  isActive: boolean;
}

const tierColorMap: Record<string, string> = {
  free: 'default',
  pro: 'blue',
  enterprise: 'gold',
};

const TenantManagement = () => {
  const {
    tenants, tenantsLoading, error,
    fetchTenants, createTenant, updateTenant, deleteTenant, clearError,
  } = useAdminStore();

  const [modalOpen, setModalOpen] = useState(false);
  const [editingTenant, setEditingTenant] = useState<TenantRecord | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [form] = Form.useForm<TenantFormValues>();

  const loadTenants = useCallback(() => {
    fetchTenants();
  }, [fetchTenants]);

  useEffect(() => {
    loadTenants();
  }, [loadTenants]);

  useEffect(() => {
    if (error) {
      message.error(error);
      clearError();
    }
  }, [error, clearError]);

  const openCreateModal = () => {
    setEditingTenant(null);
    form.resetFields();
    form.setFieldsValue({
      name: '',
      slug: '',
      tier: 'free',
      isActive: true,
    });
    setModalOpen(true);
  };

  const openEditModal = (record: TenantRecord) => {
    setEditingTenant(record);
    form.setFieldsValue({
      name: record.name,
      slug: record.slug,
      tier: record.tier,
      isActive: record.isActive,
    });
    setModalOpen(true);
  };

  const handleCloseModal = () => {
    setModalOpen(false);
    setEditingTenant(null);
    form.resetFields();
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setConfirmLoading(true);

      if (editingTenant) {
        await updateTenant(editingTenant.id, {
          name: values.name,
          slug: values.slug,
          tier: values.tier,
          isActive: values.isActive,
        });
        message.success('租户更新成功。');
      } else {
        await createTenant({
          name: values.name,
          slug: values.slug,
          tier: values.tier,
          isActive: values.isActive,
        });
        message.success('租户创建成功。');
      }

      handleCloseModal();
    } catch (err: any) {
      if (err?.errorFields) {
        // Form validation error — do not show extra message
        return;
      }
      message.error(err?.message || '发生错误。');
    } finally {
      setConfirmLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteTenant(id);
      message.success('租户删除成功。');
    } catch (err: any) {
      message.error(err?.message || '删除租户失败。');
    }
  };

  const handleToggleActive = async (id: string, isActive: boolean) => {
    try {
      await updateTenant(id, { isActive });
      message.success(`租户已${isActive ? '启用' : '停用'}。`);
    } catch (err: any) {
      message.error(err?.message || '更新租户状态失败。');
    }
  };

  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const nameValue = e.target.value;
    const slugValue = nameValue
      .toLowerCase()
      .replace(/\s+/g, '-')
      .replace(/[^a-z0-9-]/g, '');
    form.setFieldsValue({
      name: nameValue,
      slug: slugValue,
    });
  };

  const columns: ColumnsType<TenantRecord> = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (text: string) => <Text strong>{text}</Text>,
    },
    {
      title: '标识',
      dataIndex: 'slug',
      key: 'slug',
      render: (text: string) => <Text code>{text}</Text>,
    },
    {
      title: '层级',
      dataIndex: 'tier',
      key: 'tier',
      render: (tier: string) => (
        <Tag color={tierColorMap[tier] || 'default'}>{tier}</Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'isActive',
      key: 'isActive',
      render: (isActive: boolean, record: TenantRecord) => (
        <Switch
          checked={isActive}
          onChange={(checked) => handleToggleActive(record.id, checked)}
          checkedChildren="活跃"
          unCheckedChildren="停用"
        />
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'createdAt',
      key: 'createdAt',
      render: (date: string) => formatDate(date),
    },
    {
      title: '操作',
      key: 'actions',
      width: 140,
      render: (_: unknown, record: TenantRecord) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => openEditModal(record)}
          />
          <Popconfirm
            title="删除租户"
            description={`确认删除 "${record.name}"？`}
            onConfirm={() => handleDelete(record.id)}
            okText="确认删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Button
              type="link"
              size="small"
              danger
              icon={<DeleteOutlined />}
            />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4 pt-4">
        <Text type="secondary">
          共 {tenants.length} 个租户
        </Text>
        <Space>
          <Button
            icon={<ReloadOutlined />}
            onClick={loadTenants}
            loading={tenantsLoading}
          >
            刷新
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={openCreateModal}
          >
            新增租户
          </Button>
        </Space>
      </div>

      <Spin spinning={tenantsLoading}>
        {tenants.length === 0 && !tenantsLoading ? (
          <Empty
            description="暂无租户"
            className="py-12"
          >
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={openCreateModal}
            >
              新增租户
            </Button>
          </Empty>
        ) : (
          <Table
            columns={columns}
            dataSource={tenants}
            rowKey="id"
            pagination={{ pageSize: 10, showSizeChanger: true }}
            scroll={{ x: 800 }}
          />
        )}
      </Spin>

      <Modal
        title={editingTenant ? '编辑租户' : '新增租户'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={handleCloseModal}
        confirmLoading={confirmLoading}
        destroyOnClose
        okText={editingTenant ? '更新' : '创建'}
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ tier: 'free', isActive: true }}
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[
              { required: true, message: '请输入租户名称。' },
              { min: 2, message: '名称至少需要 2 个字符。' },
            ]}
          >
            <Input
              placeholder="例如: Acme Corp"
              onChange={handleNameChange}
            />
          </Form.Item>

          <Form.Item
            name="slug"
            label="标识"
            rules={[
              { required: true, message: '请输入标识。' },
              {
                pattern: /^[a-z0-9-]+$/,
                message: '标识仅允许小写字母、数字和连字符。',
              },
            ]}
          >
            <Input placeholder="根据名称自动生成" />
          </Form.Item>

          <Form.Item
            name="tier"
            label="层级"
            rules={[{ required: true, message: '请选择层级。' }]}
          >
            <Select
              options={[
                { value: 'free', label: '免费' },
                { value: 'pro', label: '专业版' },
                { value: 'enterprise', label: '企业版' },
              ]}
            />
          </Form.Item>

          <Form.Item
            name="isActive"
            label="活跃"
            valuePropName="checked"
          >
            <Switch checkedChildren="活跃" unCheckedChildren="停用" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default TenantManagement;
