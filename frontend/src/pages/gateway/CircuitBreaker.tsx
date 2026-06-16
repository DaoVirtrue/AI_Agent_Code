import { Card, Progress, Typography, Tag, Tooltip } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  WarningOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons';
import { formatDate } from '@/utils/format';

const { Text } = Typography;

interface CircuitBreakerProps {
  providerName: string;
  state: 'CLOSED' | 'OPEN' | 'HALF_OPEN';
  failureCount: number;
  lastTransitionTime: string;
}

const stateConfig: Record<
  string,
  {
    strokeColor: string;
    icon: React.ReactNode;
    label: string;
    description: string;
    tooltip: string;
    progressColor: string;
  }
> = {
  CLOSED: {
    strokeColor: '#52c41a',
    progressColor: '#52c41a',
    icon: <CheckCircleOutlined className="text-green-500 text-lg" />,
    label: '正常',
    description: '运行正常',
    tooltip:
      '熔断器处于关闭状态，所有请求正常放行。熔断器正在监控故障。',
  },
  OPEN: {
    strokeColor: '#ff4d4f',
    progressColor: '#ff4d4f',
    icon: <CloseCircleOutlined className="text-red-500 text-lg" />,
    label: '已熔断',
    description: '请求被拦截',
    tooltip:
      '熔断器已打开，所有请求被立即拒绝以保护 Provider 并留出恢复时间。',
  },
  HALF_OPEN: {
    strokeColor: '#faad14',
    progressColor: '#faad14',
    icon: <WarningOutlined className="text-orange-500 text-lg" />,
    label: '半开检测中',
    description: '检测恢复',
    tooltip:
      '熔断器处于半开状态，允许少量试探性请求通过以检测 Provider 是否已恢复。',
  },
};

export default function CircuitBreaker({
  providerName,
  state,
  failureCount,
  lastTransitionTime,
}: CircuitBreakerProps) {
  const config = stateConfig[state] || stateConfig.CLOSED;

  const progressPercent =
    state === 'OPEN' ? 100 : state === 'HALF_OPEN' ? 50 : 0;

  return (
    <Card
      className="h-full shadow-sm hover:shadow-md transition-shadow duration-300"
      bodyStyle={{ padding: '16px' }}
    >
      {/* Provider Name */}
      <div className="flex items-center gap-2 mb-3">
        <ClockCircleOutlined className="text-blue-500" />
        <Text strong className="text-base">
          {providerName}
        </Text>
      </div>

      {/* Circular State Indicator */}
      <div className="flex justify-center py-2">
        <Tooltip title={config.tooltip} placement="top">
          <div className="flex flex-col items-center gap-1">
            <Progress
              type="circle"
              percent={progressPercent}
              size={100}
              strokeColor={config.strokeColor}
              strokeWidth={6}
              format={() => state}
              strokeLinecap="round"
            />
          </div>
        </Tooltip>
      </div>

      {/* State Label */}
      <div className="flex items-center justify-center gap-2 mt-2 mb-3">
        {config.icon}
        <Text
          strong
          style={{ color: config.strokeColor }}
          className="text-sm"
        >
          {config.label}
        </Text>
        <Text type="secondary" className="text-xs">
          - {config.description}
        </Text>
      </div>

      {/* Divider */}
      <div className="border-t border-gray-100 my-3" />

      {/* Info Section */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ExclamationCircleOutlined
              className={
                failureCount > 0 ? 'text-red-500' : 'text-gray-400'
              }
            />
            <Text type="secondary" className="text-xs">
              故障次数
            </Text>
          </div>
          <Tag
            color={failureCount > 0 ? 'red' : 'green'}
            className="text-xs"
          >
            {failureCount}
          </Tag>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ClockCircleOutlined className="text-gray-400" />
            <Text type="secondary" className="text-xs">
              上次切换
            </Text>
          </div>
          <Tooltip title={formatDate(lastTransitionTime)}>
            <Text className="text-xs" code>
              {formatDate(lastTransitionTime, 'MM-DD HH:mm')}
            </Text>
          </Tooltip>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircleOutlined
              className={state === 'CLOSED' ? 'text-green-500' : 'text-gray-400'}
            />
            <Text type="secondary" className="text-xs">
              状态
            </Text>
          </div>
          <Tag
            color={
              state === 'CLOSED'
                ? 'green'
                : state === 'OPEN'
                  ? 'red'
                  : 'orange'
            }
            className="text-xs"
          >
            {state}
          </Tag>
        </div>
      </div>
    </Card>
  );
}
