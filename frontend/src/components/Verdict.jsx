const isBuy = (verdict) => verdict === 'BUY'

const factorColor = (score) => {
  if (score >= 70) return '#48bb78'
  if (score >= 45) return '#ed8936'
  return '#f56565'
}

export default function Verdict({ verdict, confidence, factors, summary }) {
  const buy = isBuy(verdict)
  const color = buy ? '#48bb78' : '#f56565'

  return (
    <div style={{
      background: '#161b27',
      border: `1px solid ${buy ? 'rgba(72,187,120,0.25)' : 'rgba(245,101,101,0.25)'}`,
      borderRadius: 12,
      padding: '24px 28px',
      display: 'grid',
      gridTemplateColumns: '280px 1fr',
      gap: 28,
    }}>
      {/* Left: verdict + confidence + factors */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#718096' }}>
          Recommendation
        </div>

        <div style={{
          textAlign: 'center',
          fontSize: 36,
          fontWeight: 900,
          letterSpacing: '-1px',
          padding: '12px 0',
          borderRadius: 10,
          background: buy ? 'rgba(72,187,120,0.12)' : 'rgba(245,101,101,0.12)',
          border: `2px solid ${buy ? 'rgba(72,187,120,0.35)' : 'rgba(245,101,101,0.35)'}`,
          color,
        }}>
          {verdict}
        </div>

        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
            <span style={{ fontSize: 11, color: '#718096', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Confidence
            </span>
            <span style={{ fontSize: 15, fontWeight: 700, color }}>
              {confidence}%
            </span>
          </div>
          <div style={{ height: 8, background: '#1e2535', borderRadius: 4 }}>
            <div style={{
              height: 8,
              borderRadius: 4,
              width: `${confidence}%`,
              background: buy
                ? 'linear-gradient(90deg, #3182ce, #48bb78)'
                : 'linear-gradient(90deg, #742a2a, #f56565)',
              transition: 'width 0.6s ease',
            }} />
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          {Object.entries(factors || {}).map(([key, { score, label }]) => (
            <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
              <span style={{ color: '#718096', width: 86, textTransform: 'capitalize', flexShrink: 0 }}>
                {key}
              </span>
              <div style={{ flex: 1, height: 5, background: '#1e2535', borderRadius: 3 }}>
                <div style={{
                  height: 5,
                  borderRadius: 3,
                  width: `${score}%`,
                  background: factorColor(score),
                  transition: 'width 0.6s ease',
                }} />
              </div>
              <span style={{ color: factorColor(score), fontWeight: 700, width: 30, textAlign: 'right', fontSize: 11 }}>
                {score}
              </span>
            </div>
          ))}
        </div>

        <p style={{ fontSize: 10, color: '#4a5568', lineHeight: 1.5, marginTop: 'auto' }}>
          Not financial advice. Based on public data &amp; quantitative signals only.
        </p>
      </div>

      {/* Right: AI analysis */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#718096' }}>
          AI Analysis
        </div>
        {summary ? (
          <div style={{
            fontSize: 14,
            color: '#cbd5e0',
            lineHeight: 1.75,
            flex: 1,
          }}>
            {summary}
          </div>
        ) : (
          <div style={{ fontSize: 13, color: '#4a5568', fontStyle: 'italic' }}>
            AI analysis unavailable.
          </div>
        )}
      </div>
    </div>
  )
}
