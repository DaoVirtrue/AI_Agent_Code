import {
  Card, Select, Row, Col, Statistic, Table, Button, Empty, Spin, message,
} from 'antd';
import {
  BarChartOutlined, DollarOutlined, ThunderboltOutlined,
  ApiOutlined, DownloadOutlined, ReloadOutlined,
} from '@ant-design/icons';
import { useEffect, useState, useCallback, useMemo } from 'react';
import { useAdminStore } from '@/store/adminStore';
import { formatNumber, formatCurrency } from '@/utils/format';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip as ReTooltip, Legend, ResponsiveContainer,
} from 'recharts';
import type { ColumnsType } from 'antd/es/table';

interface ModelBreakdown {
  model: string;
  calls: number;
  tokens: number;
  cost: number;
}

interface DailyUsageRow {
  date: string;
  calls: number;
  tokens: number;
}

const periodOptions = [
  { value: '7d', label: '最近 7 天' },
  { value: '30d', label: '最近 30 天' },
  { value: '90d', label: '最近 90 天' },
];

const COLORS = {
  calls: '#1677ff',
  tokens: '#52c41a',
};

const UsageReport = () => {
  const {
    usageStats, dailyUsage, modelBreakdown, usageLoading, error,
    fetchUsageReport, clearError,
  } = useAdminStore();

  const [period, setPeriod] = useState<string>('30d');
  const [breakdownSortKey, setBreakdownSortKey] = useState<string>('calls');
  const [breakdownSortOrder, setBreakdownSortOrder] = useState<'ascend' | 'descend'>('descend');

  const loadReport = useCallback(
    (p: string) => {
      fetchUsageReport(p);
    },
    [fetchUsageReport],
  );

  useEffect(() => {
    loadReport(period);
  }, [loadReport, period]);

  useEffect(() => {
    if (error) {
      message.error(error);
      clearError();
    }
  }, [error, clearError]);

  const handlePeriodChange = (value: string) => {
    setPeriod(value);
  };

  const activeModelsCount = useMemo(() => {
    return (modelBreakdown || []).length;
  }, [modelBreakdown]);

  const handleExportCSV = () => {
    if (!modelBreakdown || modelBreakdown.length === 0) {
      message.warning('无数据可导出。');
      return;
    }

    const headers = ['模型', '调用数', 'Token 数', '费用'];
    const rows = modelBreakdown.map((item: ModelBreakdown) => [
      item.model,
      item.calls,
      item.tokens,
      item.cost,
    ]);

    const csvContent = [
      headers.join(','),
      ...rows.map((row) => row.join(',')),
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `usage-report-${period}-${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    message.success('报告已导出为 CSV。');
  };

  const breakdownColumns: ColumnsType<ModelBreakdown> = [
    {
      title: '模型',
      dataIndex: 'model',
      key: 'model',
      width: 200,
    },
    {
      title: '调用数',
      dataIndex: 'calls',
      key: 'calls',
      sorter: (a, b) => a.calls - b.calls,
      render: (val: number) => formatNumber(val),
    },
    {
      title: 'Token 数',
      dataIndex: 'tokens',
      key: 'tokens',
      sorter: (a, b) => a.tokens - b.tokens,
      render: (val: number) => formatNumber(val),
    },
    {
      title: '费用',
      dataIndex: 'cost',
      key: 'cost',
      sorter: (a, b) => a.cost - b.cost,
      render: (val: number) => formatCurrency(val),
    },
  ];

  const hasDailyData = (dailyUsage || []).length > 0;
  const hasBreakdownData = (modelBreakdown || []).length > 0;

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-white shadow-lg border rounded-md p-3 text-sm">
          <p className="font-semibold mb-1">{label}</p>
          {payload.map((entry: any, idx: number) => (
            <p key={idx} style={{ color: entry.color }}>
              {entry.name}: {entry.name === 'Token 数' ? formatNumber(entry.value) : entry.value}
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="pt-4">
      {/* Controls Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <Select
          value={period}
          onChange={handlePeriodChange}
          options={periodOptions}
          style={{ width: 180 }}
        />
        <Space>
          <Button
            icon={<DownloadOutlined />}
            onClick={handleExportCSV}
            disabled={!hasBreakdownData}
          >
            导出 CSV
          </Button>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => loadReport(period)}
            loading={usageLoading}
          >
            刷新
          </Button>
        </Space>
      </div>

      <Spin spinning={usageLoading}>
        {!usageStats && !usageLoading ? (
          <Empty description="暂无用量数据。" className="py-12" />
        ) : (
          <>
            {/* Summary Cards */}
            <Row gutter={[16, 16]} className="mb-6">
              <Col xs={24} sm={12} lg={6}>
                <Card>
                  <Statistic
                    title="总调用"
                    value={usageStats?.totalCalls ?? 0}
                    prefix={<ApiOutlined />}
                    formatter={(val) => formatNumber(val as number)}
                  />
                </Card>
              </Col>
              <Col xs={24} sm={12} lg={6}>
                <Card>
                  <Statistic
                    title="Token 总量"
                    value={usageStats?.totalTokens ?? 0}
                    prefix={<ThunderboltOutlined />}
                    formatter={(val) => formatNumber(val as number)}
                  />
                </Card>
              </Col>
              <Col xs={24} sm={12} lg={6}>
                <Card>
                  <Statistic
                    title="总费用"
                    value={usageStats?.totalCost ?? 0}
                    prefix={<DollarOutlined />}
                    precision={4}
                    formatter={(val) => formatCurrency(val as number)}
                  />
                </Card>
              </Col>
              <Col xs={24} sm={12} lg={6}>
                <Card>
                  <Statistic
                    title="活跃模型"
                    value={activeModelsCount}
                    prefix={<BarChartOutlined />}
                  />
                </Card>
              </Col>
            </Row>

            {/* Bar Chart */}
            <Card
              title="用量趋势"
              className="mb-6"
              extra={
                !hasDailyData && (
                  <span className="text-gray-400 text-sm">无数据</span>
                )
              }
            >
              {hasDailyData ? (
                <ResponsiveContainer width="100%" height={360}>
                  <BarChart
                    data={dailyUsage}
                    margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" fontSize={12} />
                    <YAxis yAxisId="left" orientation="left" fontSize={12} />
                    <YAxis yAxisId="right" orientation="right" fontSize={12} />
                    <ReTooltip content={<CustomTooltip />} />
                    <Legend />
                    <Bar
                      yAxisId="left"
                      dataKey="calls"
                      name="调用数"
                      fill={COLORS.calls}
                      radius={[4, 4, 0, 0]}
                    />
                    <Bar
                      yAxisId="right"
                      dataKey="tokens"
                      name="Token 数"
                      fill={COLORS.tokens}
                      radius={[4, 4, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex items-center justify-center h-[360px] text-gray-400">
                  暂无每日用量数据。
                </div>
              )}
            </Card>

            {/* Breakdown Table */}
            <Card title="按模型用量">
              {hasBreakdownData ? (
                <Table
                  columns={breakdownColumns}
                  dataSource={modelBreakdown}
                  rowKey="model"
                  pagination={{ pageSize: 10, showSizeChanger: true }}
                  scroll={{ x: 600 }}
                />
              ) : (
                <Empty description="暂无模型用量明细。" />
              )}
            </Card>
          </>
        )}
      </Spin>
    </div>
  );
};

export default UsageReport;
