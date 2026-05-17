const signalStyle = (signal) => {
  if (signal === 'BUY')  return { background: 'rgba(72,187,120,0.15)', color: '#48bb78', border: '1px solid rgba(72,187,120,0.3)' }
  if (signal === 'SELL') return { background: 'rgba(245,101,101,0.15)', color: '#f56565', border: '1px solid rgba(245,101,101,0.3)' }
  return { background: 'rgba(237,137,54,0.15)', color: '#ed8936', border: '1px solid rgba(237,137,54,0.3)' }
}

const Row = ({ label, value, sub, valueColor }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '9px 0', borderBottom: '1px solid #1e2535', fontSize: 13 }}>
    <span style={{ color: '#718096' }}>{label}</span>
    <span style={{ fontWeight: 600, color: valueColor || '#e2e8f0' }}>
      {value}
      {sub && <span style={{ fontSize: 11, marginLeft: 6, color: sub.color || '#718096' }}>{sub.text}</span>}
    </span>
  </div>
)

export default function Technical({ technicals: t }) {
  if (!t || Object.keys(t).length === 0) return null

  const rsiLabel = t.rsi == null ? '' : t.rsi > 70 ? 'Overbought' : t.rsi < 30 ? 'Oversold' : 'Neutral'
  const rsiColor = t.rsi > 70 ? '#f56565' : t.rsi < 30 ? '#48bb78' : '#ed8936'

  const bbLabel = { upper: 'Near upper band', mid: 'Mid-range', lower: 'Near lower band' }[t.bb_position] || '—'

  const volPct = t.volume_vs_avg != null ? `${t.volume_vs_avg >= 0 ? '+' : ''}${(t.volume_vs_avg * 100).toFixed(0)}% vs avg` : 'N/A'
  const volColor = t.volume_vs_avg > 0 ? '#48bb78' : '#f56565'

  return (
    <div style={{
      background: '#161b27',
      border: '1px solid #2d3748',
      borderRadius: 12,
      padding: '20px 24px',
    }}>
      <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#718096', marginBottom: 16 }}>
        Technical Indicators
      </div>

      <Row label="RSI (14)"
           value={t.rsi != null ? t.rsi.toFixed(1) : 'N/A'}
           sub={{ text: rsiLabel, color: rsiColor }} />

      <Row label="MACD"
           value={t.macd_bullish == null ? 'N/A' : t.macd_bullish ? 'Bullish crossover' : 'Bearish crossover'}
           valueColor={t.macd_bullish == null ? '#e2e8f0' : t.macd_bullish ? '#48bb78' : '#f56565'} />

      <Row label="50-Day MA"
           value={t.sma_50 != null ? `$${t.sma_50.toFixed(2)}` : 'N/A'}
           sub={t.above_sma_50 != null ? { text: t.above_sma_50 ? '↑ Above' : '↓ Below', color: t.above_sma_50 ? '#48bb78' : '#f56565' } : null} />

      <Row label="200-Day MA"
           value={t.sma_200 != null ? `$${t.sma_200.toFixed(2)}` : 'N/A'}
           sub={t.above_sma_200 != null ? { text: t.above_sma_200 ? '↑ Above' : '↓ Below', color: t.above_sma_200 ? '#48bb78' : '#f56565' } : null} />

      <Row label="Bollinger Bands" value={bbLabel} />

      <Row label="Volume vs Avg" value={volPct} valueColor={volColor} />

      <Row label="Support (20d)" value={t.support != null ? `$${t.support.toFixed(2)}` : 'N/A'} />

      <Row label="Resistance (20d)" value={t.resistance != null ? `$${t.resistance.toFixed(2)}` : 'N/A'} />

      <div style={{ marginTop: 16, display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ fontSize: 12, color: '#718096' }}>Technical Signal:</span>
        <span style={{
          fontSize: 13,
          fontWeight: 700,
          padding: '4px 12px',
          borderRadius: 6,
          ...signalStyle(t.signal),
        }}>
          {t.signal === 'BUY' ? '▲' : t.signal === 'SELL' ? '▼' : '—'} {t.signal}
        </span>
        <span style={{ fontSize: 11, color: '#4a5568' }}>({t.bullish_signals ?? 0}/4 bullish signals)</span>
      </div>
    </div>
  )
}
