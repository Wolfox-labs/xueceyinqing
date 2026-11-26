import { PieChart as RechartsPieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'

interface PieChartProps {
  data: { labels: string[]; values: number[] } | null
}

const COLORS = ['#61afef', '#98c379', '#e5c07b', '#e06c75', '#c678dd', '#56b6c2']

export default function PieChart({ data }: PieChartProps) {
  if (!data || data.labels.length === 0) {
    return <div className="text-tertiary text-sm text-center py-12">暂无数据</div>
  }

  const chartData = data.labels.map((label, i) => ({
    name: label,
    value: data.values[i] ?? 0,
  }))

  return (
    <ResponsiveContainer width="100%" height={280}>
      <RechartsPieChart>
        <Pie
          data={chartData}
          cx="50%"
          cy="50%"
          innerRadius={60}
          outerRadius={100}
          paddingAngle={2}
          dataKey="value"
          stroke="none"
        >
          {chartData.map((_, i) => (
            <Cell key={i} fill={COLORS[i % COLORS.length]} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            backgroundColor: 'var(--color-bg-secondary)',
            border: '1px solid var(--color-border)',
            borderRadius: '8px',
            color: 'var(--color-text-primary)',
          }}
          formatter={(value) => `${value}%`}
        />
      </RechartsPieChart>
    </ResponsiveContainer>
  )
}
