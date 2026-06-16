import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { Empty } from 'antd';
import { formatNumber } from '@/utils/format';

const COLORS = [
  '#1677ff', '#722ed1', '#52c41a', '#fa8c16', '#eb2f96',
  '#13c2c2', '#f5222d', '#2f54eb', '#faad14', '#a0d911',
];

interface ModelDistributionChartProps {
  data: Array<{ model: string; tokens: number }>;
  height?: number;
}

export function ModelDistributionChart({ data, height = 350 }: ModelDistributionChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center" style={{ height }}>
        <Empty description="暂无模型分布数据" />
      </div>
    );
  }

  const renderLabel = ({ name, percent }: { name: string; percent: number }) =>
    `${name} ${(percent * 100).toFixed(0)}%`;

  return (
    <div className="w-full">
      <h3 className="text-base font-semibold text-gray-900 dark:text-white mb-4">
        模型分布
      </h3>
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            labelLine={false}
            label={renderLabel}
            outerRadius={110}
            innerRadius={55}
            dataKey="tokens"
            nameKey="model"
          >
            {data.map((_entry, index) => (
              <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              borderRadius: 8,
              border: '1px solid #e8e8e8',
              boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
            }}
            formatter={(value: number, name: string) => [
              `${formatNumber(value, 0)} tokens`,
              name,
            ]}
          />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
