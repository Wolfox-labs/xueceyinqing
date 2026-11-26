import {
  RadarChart as RechartsRadar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
} from 'recharts'

interface RadarChartProps {
  data: { labels: string[]; values: number[] } | null
}

const COLORS = ['#61afef', '#98c379', '#e5c07b', '#e06c75', '#c678dd', '#56b6c2']

/** 轴标签最长字符数。
 *
 * 真实故障：30 个知识点（名字长达 20+ 字，如"单符号位补码加法的溢出表现（正溢/负溢）"）
 * 全部当轴标签时，recharts 沿圆周排不下，实测 12 处互相重叠，图完全不可读。
 * 这里截断显示；完整名字通过 <title> 悬浮可见，信息不丢。
 */
const MAX_TICK_CHARS = 9

function shorten(label: string): string {
  const text = (label || '').trim()
  return text.length > MAX_TICK_CHARS ? `${text.slice(0, MAX_TICK_CHARS)}…` : text
}

export default function RadarChart({ data }: RadarChartProps) {
  if (!data || data.labels.length === 0) {
    return <div className="text-tertiary text-sm text-center py-12">暂无数据</div>
  }

  const chartData = data.labels.map((label, i) => ({
    subject: shorten(label),
    fullName: label,
    value: data.values[i] ?? 0,
    fullMark: 100,
  }))

  return (
    <ResponsiveContainer width="100%" height={300}>
      <RechartsRadar data={chartData}>
        <PolarGrid stroke="var(--color-border)" strokeOpacity={0.75} />
        <PolarAngleAxis
          dataKey="subject"
          tick={{ fill: 'var(--color-text-tertiary)', fontSize: 11 }}
        />
        <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fill: 'var(--color-text-tertiary)', fontSize: 10 }} />
        <Radar
          name="score"
          dataKey="value"
          stroke={COLORS[0]}
          fill={COLORS[0]}
          fillOpacity={0.2}
        />
      </RechartsRadar>
    </ResponsiveContainer>
  )
}

