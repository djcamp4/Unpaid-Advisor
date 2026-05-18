const DECISION_STYLE = {
  'BUY':       { color: '#48bb78', bg: 'rgba(72,187,120,0.12)',  border: 'rgba(72,187,120,0.3)'  },
  'HOLD':      { color: '#ed8936', bg: 'rgba(237,137,54,0.12)', border: 'rgba(237,137,54,0.3)'  },
  "DON'T BUY": { color: '#f56565', bg: 'rgba(245,101,101,0.12)', border: 'rgba(245,101,101,0.3)' },
}

function decisionStyle(d) {
  return DECISION_STYLE[d] || DECISION_STYLE['HOLD']
}

function AgentCard({ label, icon, caseText, decision, accentColor }) {
  const ds = decisionStyle(decision)
  return (
    <div style={{
      background: '#161b27',
      border: '1px solid #2d3748',
      borderRadius: 12,
      padding: '20px 22px',
      display: 'flex',
      flexDirection: 'column',
      gap: 14,
    }}>
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ fontSize: 16 }}>{icon}</span>
        <div style={{ fontSize: 13, fontWeight: 700, color: accentColor }}>
          {label}
        </div>
        <div style={{
          marginLeft: 'auto',
          fontSize: 12,
          fontWeight: 800,
          padding: '4px 12px',
          borderRadius: 6,
          background: ds.bg,
          border: `1px solid ${ds.border}`,
          color: ds.color,
          whiteSpace: 'nowrap',
        }}>
          {decision}
        </div>
      </div>

      {/* Case text */}
      <div style={{ fontSize: 13, color: '#a0aec0', lineHeight: 1.75 }}>
        {caseText}
      </div>
    </div>
  )
}

export default function Debate({ debate }) {
  if (!debate) return null

  const { summary, value, growth } = debate

  return (
    <div style={{
      background: '#161b27',
      border: '1px solid #2d3748',
      borderRadius: 12,
      padding: '22px 24px',
      display: 'flex',
      flexDirection: 'column',
      gap: 20,
    }}>
      {/* Two agent cards */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <AgentCard
          label="Growth Investor"
          icon="🚀"
          caseText={growth.case}
          decision={growth.decision}
          accentColor="#9f7aea"
        />
        <AgentCard
          label="Value Investor"
          icon="📊"
          caseText={value.case}
          decision={value.decision}
          accentColor="#63b3ed"
        />
      </div>

      {/* Divider */}
      {summary && <div style={{ borderTop: '1px solid #2d3748' }} />}

      {/* Summary paragraph */}
      {summary && (
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#718096', marginBottom: 10 }}>
            Analysis
          </div>
          <div style={{ fontSize: 14, color: '#cbd5e0', lineHeight: 1.8 }}>
            {summary}
          </div>
        </div>
      )}
    </div>
  )
}
