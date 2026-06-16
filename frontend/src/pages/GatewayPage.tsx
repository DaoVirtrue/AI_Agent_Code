import { useEffect, useState } from 'react';
import { Card, Table, Typography, Row, Col, Tag, Statistic, Empty, Spin, Progress } from 'antd';
import { ApiOutlined, CheckCircleOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { useAppStore, useGatewayStore } from '@/store';
import type { ModelInfo } from '@/types';
import { StatusBadge } from '@/components/common/StatusBadge';
import { formatCurrency, formatNumber, formatDuration } from '@/utils/format';

const { Title, Text } = Typography;

interface ProviderHealth {
  provider: string;
  status: 'healthy' | 'degraded' | 'unhealthy';
  latency: number;
  successRate: number;
}

export function GatewayPage() {
  const setBreadcrumbs = useAppStore((s) => s.setBreadcrumbs);
  const [providers, setProviders] = useState<ProviderHealth[]>([]);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setBreadcrumbs([{ title: 'Gateway' }]);
  }, [setBreadcrumbs]);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const { fetchProviders, fetchModels } = useGatewayStore.getState();
      await fetchProviders();
      await fetchModels();
      const state = useGatewayStore.getState();
      setProviders(state.providers);
      setModels(state.models);
    } catch {
      setProviders([]);
      setModels([]);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Spin size="large" tip="正在加载网关数据..." />
      </div>
    );
  }

  const statusColor = (status: string) => {
    switch (status) {
      case 'healthy': return '#52c41a';
      case 'degraded': return '#fa8c16';
      case 'unhealthy': return '#f5222d';
      default: return '#d9d9d9';
    }
  };

  const columns = [
    {
      title: '模型',
      dataIndex: 'name',
      key: 'name',
      render: (text: string, record: ModelInfo) => (
        <div>
          <Text strong>{text}</Text>
          <br />
          <Text type="secondary" className="text-xs">{record.id}</Text>
        </div>
      ),
    },
    {
      title: 'Provider',
      dataIndex: 'provider',
      key: 'provider',
      render: (provider: string) => <Tag>{provider}</Tag>,
    },
    {
      title: 'Max Tokens',
      dataIndex: 'max_tokens',
      key: 'max_tokens',
      render: (val: number) => formatNumber(val, 0),
    },
    {
      title: '输入成本 /1K',
      dataIndex: 'cost_per_1k_input',
      key: 'cost_per_1k_input',
      render: (val: number) => formatCurrency(val),
    },
    {
      title: '输出成本 /1K',
      dataIndex: 'cost_per_1k_output',
      key: 'cost_per_1k_output',
      render: (val: number) => formatCurrency(val),
    },
    {
      title: '流式',
      dataIndex: 'supports_streaming',
      key: 'supports_streaming',
      render: (val: boolean) => val ? <CheckCircleOutlined className="text-green-500" /> : <Tag color="red">否</Tag>,
    },
    {
      title: '工具',
      dataIndex: 'supports_tools',
      key: 'supports_tools',
      render: (val: boolean) => val ? <CheckCircleOutlined className="text-green-500" /> : <Tag color="red">否</Tag>,
    },
  ];

  return (
    <div className="space-y-6 animate-fade-in">
      <Title level={4} className="!mb-0">AI Gateway</Title>

      {/* Provider Health Cards */}
      <div>
        <Text strong className="block mb-3 text-base">Provider 健康状态</Text>
        <Row gutter={[16, 16]}>
          {providers.map((p) => (
            <Col xs={24} sm={12} md={8} lg={6} key={p.provider}>
              <Card
                className="h-full"
                style={{ borderTop: `3px solid ${statusColor(p.status)}` }}
              >
                <div className="flex items-center justify-between mb-3">
                  <Text strong className="text-base">{p.provider}</Text>
                  <StatusBadge status={p.status} />
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <Text type="secondary">延迟</Text>
                    <Text strong>{p.latency > 0 ? p.latency.toFixed(0) + 'ms' : '未测量'}</Text>
                  </div>
                  <div className="flex justify-between text-sm">
                    <Text type="secondary">成功率</Text>
                    <Text strong>{p.successRate}%</Text>
                  </div>
                  <Progress
                    percent={p.successRate}
                    strokeColor={statusColor(p.status)}
                    size="small"
                    showInfo={false}
                  />
                </div>
              </Card>
            </Col>
          ))}
        </Row>
      </div>

      {/* Model List */}
      <Card title={<span className="flex items-center gap-2"><ThunderboltOutlined /> 可用模型</span>}>
        {models.length === 0 ? (
          <Empty description="无法获取网关数据，请检查后端服务" />
        ) : (
          <Table
            dataSource={models}
            columns={columns}
            rowKey="id"
            pagination={{ pageSize: 10 }}
            scroll={{ x: 900 }}
            size="middle"
          />
        )}
      </Card>

      {/* Circuit Breaker Status (placeholder) */}
      <Card title="断路器状态">
        <div className="p-4 text-center">
          <Text type="secondary">
            断路器监控提供 Provider 故障转移状态的实时视图。
            请在管理设置中配置断路器阈值。
          </Text>
        </div>
      </Card>
    </div>
  );
}
