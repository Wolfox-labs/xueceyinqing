import {
  LineChart as RechartsLineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'

interface LineChartProps {
  data: { labels: string[]; values: number[] } | null
}

const COLORS = ['#61afef', '#98c379', '#e5c07b', '#e06c75', '#c678dd', '#56b6c2']

export default function LineChart({ data }: LineChartProps) {
  if (!data || data.labels.length === 0) {
    return <div className="text-tertiary text-sm text-center py-12">暂无数据</div>
  }

  const chartData = data.labels.map((label, i) => ({
    name: label,
    value: data.values[i] ?? 0,
  }))

  return (
    <ResponsiveContainer width="100%" height={280}>
      <RechartsLineChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" strokeOpacity={0.75} />
        <XAxis dataKey="name" tick={{ fill: 'var(--color-text-tertiary)', fontSize: 12 }} />
        <YAxis tick={{ fill: 'var(--color-text-tertiary)', fontSize: 12 }} />
        <Tooltip
          contentStyle={{
            backgroundColor: 'var(--color-bg-secondary)',
            border: '1px solid var(--color-border)',
            borderRadius: '8px',
            color: 'var(--color-text-primary)',
          }}
        />
        <Line
          type="monotone"
          dataKey="value"
          stroke={COLORS[0]}
          strokeWidth={2}
          dot={{ r: 3, fill: COLORS[0] }}
          activeDot={{ r: 5 }}
        />
      </RechartsLineChart>
    </ResponsiveContainer>
  )
}

