const isBuy = (verdict) => verdict === 'BUY'

const factorColor = (score) => {
  if (score >= 70) return '#48bb78'
  if (score >= 45) return '#ed8936'
  return '#f56565'
}

export default function Verdict({ verdict, confidence, factors }) {
  const buy = isBuy(verdict)
  const color = buy ? '#48bb78' : '#f56565'

  return (
    <div style={{
      background: '#161b27',
      border: `1px solid ${buy ? 'rgba(72,187,120,0.25)' : 'rgba(245,101,101,0.25)'}`,
      borderRadius: 12,
      padding: '20px 24px',
      display: 'grid',
      gridTemplateColumns: 'auto 1fr auto',
      gap: 28,
      alignItems: 'center',
    }}>
      {/* Verdict badge */}
      <div style={{
        fontSize: 28,
        fontWeight: 900,
        letterSpacing: '-0.5px',
        padding: '10px 24px',
        borderRadius: 10,
        background: buy ? 'rgba(72,187,120,0.12)' : 'rgba(245,101,101,0.12)',
        border: `2px solid ${buy ? 'rgba(72,187,120,0.35)' : 'rgba(245,101,101,0.35)'}`,
        color,
        whiteSpace: 'nowrap',
      }}>
        {verdict}
      </div>

      {/* Confidence bar */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
          <span style={{ fontSize: 11, color: '#718096', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Confidence
          </span>
          <span style={{ fontSize: 14, fontWeight: 700, color }}>{confidence}%</span>
        </div>
        <div style={{ height: 7, background: '#1e2535', borderRadius: 4 }}>
          <div style={{
            height: 7,
            borderRadius: 4,
            width: `${confidence}%`,
            background: buy
              ? 'linear-gradient(90deg, #3182ce, #48bb78)'
              : 'linear-gradient(90deg, #742a2a, #f56565)',
            transition: 'width 0.6s ease',
          }} />
        </div>
      </div>

      {/* Factor mini bars */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 5, minWidth: 200 }}>
        {Object.entries(factors || {}).map(([key, { score }]) => (
          <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11 }}>
            <span style={{ color: '#718096', width: 82, textTransform: 'capitalize', flexShrink: 0 }}>
              {key}
            </span>
            <div style={{ flex: 1, height: 4, background: '#1e2535', borderRadius: 2 }}>
              <div style={{
                height: 4,
                borderRadius: 2,
                width: `${score}%`,
                background: factorColor(score),
                transition: 'width 0.6s ease',
              }} />
            </div>
            <span style={{ color: factorColor(score), fontWeight: 700, width: 28, textAlign: 'right' }}>
              {score}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
