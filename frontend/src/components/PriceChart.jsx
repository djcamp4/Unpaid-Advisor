import { useState, useMemo } from 'react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'

const RANGES = [
  { label: '1W', days: 5,   weekly: false },
  { label: '1M', days: 21,  weekly: false },
  { label: '3M', days: 63,  weekly: false },
  { label: '1Y', days: 252, weekly: false },
  { label: '5Y', days: null, weekly: true },
]

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: '#1e2535',
      border: '1px solid #2d3748',
      borderRadius: 8,
      padding: '8px 12px',
      fontSize: 12,
    }}>
      <div style={{ color: '#718096', marginBottom: 4 }}>{label}</div>
      <div style={{ fontWeight: 700 }}>${payload[0].value?.toFixed(2)}</div>
    </div>
  )
}

export default function PriceChart({ history }) {
  const [range, setRange] = useState('3M')

  const chartData = useMemo(() => {
    if (!history) return []
    const cfg = RANGES.find(r => r.label === range)
    const source = cfg.weekly ? history.weekly : history.daily
    if (!source?.length) return []
    const sliced = cfg.days ? source.slice(-cfg.days) : source
    return sliced.map(d => ({ date: d.date, close: d.close }))
  }, [history, range])

  const isUp = chartData.length >= 2 && chartData[chartData.length - 1].close >= chartData[0].close
  const lineColor = isUp ? '#48bb78' : '#f56565'
  const gradStop = isUp ? 'rgba(72,187,120,0.18)' : 'rgba(245,101,101,0.18)'

  const formatXAxis = (dateStr) => {
    const d = new Date(dateStr)
    if (range === '1W' || range === '1M') return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    if (range === '3M' || range === '1Y') return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short' })
  }

  const tickCount = range === '1W' ? 5 : range === '1M' ? 6 : range === '3M' ? 6 : 7

  return (
    <div style={{
      background: '#161b27',
      border: '1px solid #2d3748',
      borderRadius: 12,
      padding: '20px 24px',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#718096' }}>
          Price History
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {RANGES.map(r => (
            <button
              key={r.label}
              onClick={() => setRange(r.label)}
              style={{
                background: range === r.label ? '#3182ce' : 'transparent',
                border: `1px solid ${range === r.label ? '#3182ce' : '#2d3748'}`,
                borderRadius: 6,
                color: range === r.label ? '#fff' : '#718096',
                cursor: 'pointer',
                fontSize: 11,
                fontWeight: 600,
                padding: '3px 9px',
              }}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {chartData.length > 0 ? (
        <ResponsiveContainer width="100%" height={260}>
          <AreaChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={lineColor} stopOpacity={0.18} />
                <stop offset="100%" stopColor={lineColor} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#1e2535" vertical={false} />
            <XAxis
              dataKey="date"
              tickFormatter={formatXAxis}
              tick={{ fill: '#4a5568', fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              interval="preserveStartEnd"
              tickCount={tickCount}
            />
            <YAxis
              domain={['auto', 'auto']}
              tick={{ fill: '#4a5568', fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={v => `$${v}`}
              width={55}
            />
            <Tooltip content={<CustomTooltip />} />
            <Area
              type="monotone"
              dataKey="close"
              stroke={lineColor}
              strokeWidth={2}
              fill="url(#priceGrad)"
              dot={false}
              activeDot={{ r: 4, fill: lineColor, strokeWidth: 0 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      ) : (
        <div style={{ height: 260, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#4a5568' }}>
          No chart data available
        </div>
      )}
    </div>
  )
}
