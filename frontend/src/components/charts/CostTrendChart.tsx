import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { Empty } from 'antd';
import { formatCurrency, formatNumber } from '@/utils/format';

interface CostTrendChartProps {
  data: Array<{ date: string; cost: number }>;
  height?: number;
}

export function CostTrendChart({ data, height = 350 }: CostTrendChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center" style={{ height }}>
        <Empty description="暂无成本数据" />
      </div>
    );
  }

  return (
    <div className="w-full">
      <h3 className="text-base font-semibold text-gray-900 dark:text-white mb-4">
        成本趋势
      </h3>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
          <defs>
            <linearGradient id="colorCost" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#52c41a" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#52c41a" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 12 }}
            tickLine={false}
            axisLine={{ stroke: '#e8e8e8' }}
          />
          <YAxis
            tick={{ fontSize: 12 }}
            tickLine={false}
            axisLine={{ stroke: '#e8e8e8' }}
            tickFormatter={(value) => `$${formatNumber(value, 2)}`}
          />
          <Tooltip
            contentStyle={{
              borderRadius: 8,
              border: '1px solid #e8e8e8',
              boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
            }}
            formatter={(value: number) => [formatCurrency(value), '费用']}
            labelFormatter={(label) => `日期: ${label}`}
          />
          <Legend />
          <Line
            type="monotone"
            dataKey="cost"
            stroke="#52c41a"
            strokeWidth={3}
            dot={{ r: 4, fill: '#52c41a' }}
            activeDot={{ r: 6 }}
            name="API 费用"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
