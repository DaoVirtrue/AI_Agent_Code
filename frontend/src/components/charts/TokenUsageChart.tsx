import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { Empty } from 'antd';
import { formatNumber } from '@/utils/format';

interface TokenUsageChartProps {
  data: Array<{ date: string; input: number; output: number }>;
  height?: number;
}

export function TokenUsageChart({ data, height = 350 }: TokenUsageChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center" style={{ height }}>
        <Empty description="暂无 Token 用量数据" />
      </div>
    );
  }

  return (
    <div className="w-full">
      <h3 className="text-base font-semibold text-gray-900 dark:text-white mb-4">
        Token 用量趋势
      </h3>
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
          <defs>
            <linearGradient id="colorInput" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#1677ff" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#1677ff" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="colorOutput" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#722ed1" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#722ed1" stopOpacity={0} />
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
            tickFormatter={(value) => formatNumber(value, 0)}
          />
          <Tooltip
            contentStyle={{
              borderRadius: 8,
              border: '1px solid #e8e8e8',
              boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
            }}
            formatter={(value: number, name: string) => [
              formatNumber(value, 0),
              name === 'input' ? '输入 Token' : '输出 Token',
            ]}
          />
          <Legend />
          <Area
            type="monotone"
            dataKey="input"
            stroke="#1677ff"
            strokeWidth={2}
            fill="url(#colorInput)"
            name="输入 Token"
          />
          <Area
            type="monotone"
            dataKey="output"
            stroke="#722ed1"
            strokeWidth={2}
            fill="url(#colorOutput)"
            name="输出 Token"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
