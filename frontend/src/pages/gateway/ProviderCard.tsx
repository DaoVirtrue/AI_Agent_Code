import { Card, Statistic, Tag, Typography, Progress, Tooltip, Space } from 'antd';
import {
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  CloseCircleOutlined,
  ThunderboltOutlined,
  ClockCircleOutlined,
  ApiOutlined,
  CloudServerOutlined,
} from '@ant-design/icons';
import { StatusBadge } from '@/components/common/StatusBadge';

const { Text, Title } = Typography;

interface ProviderCardProps {
  provider: {
    name: string;
    status: 'healthy' | 'degraded' | 'unhealthy' | 'unknown';
    latencyP50: number;
    latencyP99: number;
    uptime: number;
    circuitState: 'CLOSED' | 'OPEN' | 'HALF_OPEN';
    failureCount: number;
    lastTransitionTime: string;
    modelCount: number;
  };
}

const circuitColorMap: Record<string, string> = {
  CLOSED: 'green',
  OPEN: 'red',
  HALF_OPEN: 'orange',
};

const circuitLabelMap: Record<string, string> = {
  CLOSED: '熔断器: 正常',
  OPEN: '熔断器: 已熔断',
  HALF_OPEN: '熔断器: 半开检测中',
};

export default function ProviderCard({ provider }: ProviderCardProps) {
  const {
    name,
    status,
    latencyP50,
    latencyP99,
    uptime,
    circuitState,
    failureCount,
    modelCount,
  } = provider;

  const uptimeLevel =
    uptime >= 99.9 ? '#52c41a' : uptime >= 99.0 ? '#faad14' : '#ff4d4f';

  return (
    <Card
      hoverable
      className="h-full transition-shadow duration-300 hover:shadow-lg"
      bodyStyle={{ padding: '20px' }}
    >
      {/* Provider Name */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <CloudServerOutlined className="text-blue-500 text-lg" />
          <Text strong className="text-lg">
            {name}
          </Text>
        </div>
        <StatusBadge status={status} />
      </div>

      {/* Latency Stats */}
      <div className="flex items-center justify-between mb-4 bg-gray-50 rounded-lg p-3">
        <Statistic
          title={
            <Space size={2}>
              <ClockCircleOutlined className="text-gray-400" />
              <Text type="secondary" className="text-xs">
                P50 延迟
              </Text>
            </Space>
          }
          value={latencyP50}
          suffix="ms"
          valueStyle={{ fontSize: '18px', fontWeight: 600 }}
        />
        <div className="w-px h-10 bg-gray-200" />
        <Statistic
          title={
            <Space size={2}>
              <ThunderboltOutlined className="text-yellow-500" />
              <Text type="secondary" className="text-xs">
                P99 延迟
              </Text>
            </Space>
          }
          value={latencyP99}
          suffix="ms"
          valueStyle={{ fontSize: '18px', fontWeight: 600 }}
        />
      </div>

      {/* Uptime */}
      <div className="flex items-center justify-between mb-3">
        <Text type="secondary" className="text-sm">
          可用率
        </Text>
        <Tooltip title={`过去 30 天可用率: ${uptime}%`}>
          <Progress
            type="circle"
            percent={uptime}
            size={60}
            strokeColor={uptimeLevel}
            format={(p) => `${(p ?? 0).toFixed(1)}%`}
            strokeWidth={8}
          />
        </Tooltip>
      </div>

      {/* Tags Row */}
      <div className="flex flex-wrap items-center gap-2 mt-3">
        <Tooltip title={`熔断器状态: ${circuitState}`}>
          <Tag color={circuitColorMap[circuitState] || 'default'}>
            {circuitState === 'CLOSED' && (
              <CheckCircleOutlined className="mr-1" />
            )}
            {circuitState === 'OPEN' && (
              <CloseCircleOutlined className="mr-1" />
            )}
            {circuitState === 'HALF_OPEN' && (
              <ExclamationCircleOutlined className="mr-1" />
            )}
            {circuitLabelMap[circuitState] || circuitState}
          </Tag>
        </Tooltip>

        <Tooltip title={`来自 ${name} 的 ${modelCount} 个可用模型`}>
          <Tag icon={<ApiOutlined />} color="blue">
            {modelCount} 个模型
          </Tag>
        </Tooltip>

        {failureCount > 0 && (
          <Tooltip title={`检测到 ${failureCount} 次最近故障`}>
            <Tag
              icon={<CloseCircleOutlined />}
              color="red"
            >
              {failureCount} 次故障
            </Tag>
          </Tooltip>
        )}
      </div>
    </Card>
  );
}
