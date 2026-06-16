import { useEffect } from 'react';
import { Row, Col, Card, Statistic, Spin, Empty } from 'antd';
import {
  ThunderboltOutlined,
  DollarOutlined,
  ClusterOutlined,
  HeartOutlined,
} from '@ant-design/icons';
import { useDashboardStore, useAppStore } from '@/store';
import { TokenUsageChart } from '@/components/charts/TokenUsageChart';
import { ModelDistributionChart } from '@/components/charts/ModelDistributionChart';
import { CostTrendChart } from '@/components/charts/CostTrendChart';
import { StatusBadge } from '@/components/common/StatusBadge';
import { formatNumber } from '@/utils/format';

export function DashboardPage() {
  const { stats, trend, distribution, costTrend, isLoading, fetchStats, fetchTrend, fetchDistribution } =
    useDashboardStore();
  const setBreadcrumbs = useAppStore((s) => s.setBreadcrumbs);

  useEffect(() => {
    setBreadcrumbs([{ title: '仪表盘' }]);
  }, [setBreadcrumbs]);

  useEffect(() => {
    fetchStats();
    fetchTrend();
    fetchDistribution();
  }, [fetchStats, fetchTrend, fetchDistribution]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Spin size="large" tip="仪表盘加载中..." />
      </div>
    );
  }

  if (!stats && !trend && !distribution && !costTrend) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Empty description="暂无仪表盘数据" />
      </div>
    );
  }

  const cardStyle: React.CSSProperties = {
    borderRadius: 12,
  };

  const iconBoxStyle = (bgColor: string): React.CSSProperties => ({
    width: 48,
    height: 48,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 8,
    background: bgColor,
  });

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Stats Row */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card style={cardStyle}>
            <Statistic
              title="Token 总量"
              value={stats?.totalTokens ?? 0}
              formatter={(val) => formatNumber(val as number, 1)}
              prefix={
                <div style={iconBoxStyle('rgba(22, 119, 255, 0.1)')}>
                  <ThunderboltOutlined style={{ fontSize: 24, color: '#1677ff' }} />
                </div>
              }
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card style={cardStyle}>
            <Statistic
              title="累计费用"
              value={stats?.totalCost ?? 0}
              precision={4}
              prefix={
                <div style={iconBoxStyle('rgba(82, 196, 26, 0.1)')}>
                  <DollarOutlined style={{ fontSize: 24, color: '#52c41a' }} />
                </div>
              }
              suffix="$"
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card style={cardStyle}>
            <Statistic
              title="活跃模型"
              value={stats?.activeModels ?? 0}
              prefix={
                <div style={iconBoxStyle('rgba(114, 46, 209, 0.1)')}>
                  <ClusterOutlined style={{ fontSize: 24, color: '#722ed1' }} />
                </div>
              }
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card style={cardStyle}>
            <div className="flex flex-col">
              <div className="text-sm text-gray-500 dark:text-gray-400 mb-2">
                健康状态
              </div>
              <div className="flex items-center gap-3">
                <div style={iconBoxStyle('rgba(245, 34, 45, 0.1)')}>
                  <HeartOutlined style={{ fontSize: 24, color: '#f5222d' }} />
                </div>
                <StatusBadge
                  status={
                    (stats?.healthStatus as
                      | 'healthy'
                      | 'degraded'
                      | 'unhealthy'
                      | 'unknown') || 'unknown'
                  }
                  showIcon
                />
              </div>
            </div>
          </Card>
        </Col>
      </Row>

      {/* Charts Row */}
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={14}>
          <Card style={cardStyle}>
            <TokenUsageChart data={trend || []} height={350} />
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card style={cardStyle}>
            <ModelDistributionChart data={distribution || []} height={350} />
          </Card>
        </Col>
      </Row>

      {/* Cost Trend */}
      <Row gutter={[16, 16]}>
        <Col span={24}>
          <Card style={cardStyle}>
            <CostTrendChart data={costTrend || []} height={350} />
          </Card>
        </Col>
      </Row>
    </div>
  );
}
