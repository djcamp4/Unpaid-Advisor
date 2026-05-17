const isBuy = (verdict) => verdict === 'BUY'

const factorColor = (score) => {
  if (score >= 70) return '#48bb78'
  if (score >= 45) return '#ed8936'
  return '#f56565'
}

export default function Verdict({ verdict, confidence, factors, summary }) {
  const buy = isBuy(verdict)

  return (
    <div style={{
      background: '#161b27',
      border: '1px solid #2d3748',
      borderRadius: 12,
      padding: '24px',
      display: 'flex',
      flexDirection: 'column',
      gap: 20,
    }}>
      <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#718096' }}>
        Recommendation
      </div>

      {/* Verdict badge */}
      <div style={{
        textAlign: 'center',
        fontSize: 38,
        fontWeight: 900,
        letterSpacing: '-1px',
        padding: '14px 0',
        borderRadius: 12,
        background: buy ? 'rgba(72,187,120,0.12)' : 'rgba(245,101,101,0.12)',
        border: `2px solid ${buy ? 'rgba(72,187,120,0.35)' : 'rgba(245,101,101,0.35)'}`,
        color: buy ? '#48bb78' : '#f56565',
      }}>
        {verdict}
      </div>

      {/* Confidence bar */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
          <span style={{ fontSize: 11, color: '#718096', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Confidence
          </span>
          <span style={{ fontSize: 16, fontWeight: 700, color: buy ? '#48bb78' : '#f56565' }}>
            {confidence}%
          </span>
        </div>
        <div style={{ height: 10, background: '#1e2535', borderRadius: 5 }}>
          <div style={{
            height: 10,
            borderRadius: 5,
            width: `${confidence}%`,
            background: buy
              ? 'linear-gradient(90deg, #3182ce, #48bb78)'
              : 'linear-gradient(90deg, #742a2a, #f56565)',
            transition: 'width 0.6s ease',
          }} />
        </div>
      </div>

      {/* Factor breakdown */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {Object.entries(factors || {}).map(([key, { score, label }]) => (
          <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
            <span style={{ color: '#718096', width: 90, textTransform: 'capitalize', flexShrink: 0 }}>
              {key}
            </span>
            <div style={{ flex: 1, height: 6, background: '#1e2535', borderRadius: 3 }}>
              <div style={{
                height: 6,
                borderRadius: 3,
                width: `${score}%`,
                background: factorColor(score),
                transition: 'width 0.6s ease',
              }} />
            </div>
            <span style={{ color: factorColor(score), fontWeight: 700, width: 32, textAlign: 'right' }}>
              {score}
            </span>
          </div>
        ))}
      </div>

      {summary && (
        <div style={{
          background: '#1a2035',
          border: '1px solid #2d3748',
          borderRadius: 8,
          padding: '12px 14px',
          fontSize: 13,
          color: '#a0aec0',
          lineHeight: 1.65,
        }}>
          <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#4a5568', marginBottom: 6 }}>
            AI Analysis
          </div>
          {summary}
        </div>
      )}

      <p style={{ fontSize: 10, color: '#4a5568', textAlign: 'center', lineHeight: 1.5 }}>
        Not financial advice. Based on public data &amp; quantitative signals only.
      </p>
    </div>
  )
}
