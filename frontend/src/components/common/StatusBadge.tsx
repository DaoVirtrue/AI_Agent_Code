import { Tag } from 'antd';
import {
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  CloseCircleOutlined,
  QuestionCircleOutlined,
  SyncOutlined,
} from '@ant-design/icons';

interface StatusBadgeProps {
  status: string;
  showIcon?: boolean;
  text?: string;
}

const statusConfig: Record<string, { color: string; icon: React.ReactNode; label: string }> = {
  healthy: { color: 'green', icon: <CheckCircleOutlined />, label: '健康' },
  degraded: { color: 'orange', icon: <ExclamationCircleOutlined />, label: '降级' },
  unhealthy: { color: 'red', icon: <CloseCircleOutlined />, label: '异常' },
  unknown: { color: 'default', icon: <QuestionCircleOutlined />, label: '未知' },
  running: { color: 'processing', icon: <SyncOutlined spin />, label: '运行中' },
  completed: { color: 'green', icon: <CheckCircleOutlined />, label: '已完成' },
  failed: { color: 'red', icon: <CloseCircleOutlined />, label: '失败' },
  pending: { color: 'default', icon: <QuestionCircleOutlined />, label: '等待中' },
  processing: { color: 'processing', icon: <SyncOutlined spin />, label: '处理中' },
  indexed: { color: 'green', icon: <CheckCircleOutlined />, label: '已索引' },
  uploading: { color: 'processing', icon: <SyncOutlined spin />, label: '上传中' },
  connected: { color: 'green', icon: <CheckCircleOutlined />, label: '已连接' },
  disconnected: { color: 'default', icon: <CloseCircleOutlined />, label: '未连接' },
  error: { color: 'red', icon: <CloseCircleOutlined />, label: '错误' },
};

export function StatusBadge({ status, showIcon = true, text }: StatusBadgeProps) {
  const config = statusConfig[status] || statusConfig.unknown;

  return (
    <Tag
      color={config.color}
      icon={showIcon ? config.icon : undefined}
      className="flex items-center gap-1 w-fit"
    >
      {text || config.label}
    </Tag>
  );
}
