import { useState } from 'react'

const STATUS_STYLE = {
  PASS:   { bg: 'rgba(72,187,120,0.12)',  color: '#48bb78', border: 'rgba(72,187,120,0.3)' },
  WARN:   { bg: 'rgba(237,137,54,0.12)', color: '#ed8936', border: 'rgba(237,137,54,0.3)' },
  FAIL:   { bg: 'rgba(245,101,101,0.12)', color: '#f56565', border: 'rgba(245,101,101,0.3)' },
  MANUAL: { bg: 'rgba(160,174,192,0.08)', color: '#a0aec0', border: 'rgba(160,174,192,0.2)' },
}

const STATUS_ICON = { PASS: '✓', WARN: '!', FAIL: '✗', MANUAL: '?' }

function StatusBadge({ status }) {
  const s = STATUS_STYLE[status] || STATUS_STYLE.MANUAL
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 8px',
      borderRadius: 5,
      fontSize: 11,
      fontWeight: 700,
      background: s.bg,
      color: s.color,
      border: `1px solid ${s.border}`,
      minWidth: 54,
      textAlign: 'center',
    }}>
      {STATUS_ICON[status]} {status}
    </span>
  )
}

function RuleRow({ rule }) {
  const [open, setOpen] = useState(false)
  const s = STATUS_STYLE[rule.status] || STATUS_STYLE.MANUAL

  return (
    <div style={{
      borderBottom: '1px solid #1e2535',
      background: open ? '#1a2035' : 'transparent',
      transition: 'background 0.15s',
    }}>
      <div
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'grid',
          gridTemplateColumns: '64px 1fr auto auto',
          gap: 12,
          alignItems: 'center',
          padding: '10px 0',
          cursor: 'pointer',
          fontSize: 13,
        }}
      >
        <span style={{ fontWeight: 700, color: '#4a5568', fontSize: 11 }}>{rule.rule_id}</span>
        <span style={{ fontWeight: 500 }}>{rule.name}</span>
        <span style={{ fontSize: 11, color: '#718096' }}>{rule.source}</span>
        <StatusBadge status={rule.status} />
      </div>

      {open && (
        <div style={{ padding: '0 0 12px 76px', fontSize: 12 }}>
          {rule.rule_type === 'qualitative' ? (
            <div style={{ color: '#a0aec0', fontStyle: 'italic' }}>{rule.threshold}</div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 6 }}>
              <div>
                <div style={{ color: '#718096', marginBottom: 2 }}>Actual</div>
                <div style={{ fontWeight: 600, color: s.color }}>{rule.actual}</div>
              </div>
              <div>
                <div style={{ color: '#718096', marginBottom: 2 }}>Threshold</div>
                <div style={{ fontWeight: 600 }}>{rule.threshold}</div>
              </div>
            </div>
          )}
          <div style={{ color: '#718096', marginTop: 4 }}>{rule.detail}</div>
        </div>
      )}
    </div>
  )
}

function PhaseSection({ phaseId, phaseName, rules }) {
  const counts = { PASS: 0, WARN: 0, FAIL: 0, MANUAL: 0 }
  rules.forEach(r => { counts[r.status] = (counts[r.status] || 0) + 1 })

  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '10px 0 6px',
        borderBottom: '2px solid #2d3748',
        marginBottom: 4,
      }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: '#63b3ed', width: 22 }}>P{phaseId}</span>
        <span style={{ fontWeight: 700, fontSize: 13 }}>{phaseName}</span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
          {counts.PASS > 0  && <span style={{ fontSize: 10, color: '#48bb78' }}>✓ {counts.PASS}</span>}
          {counts.WARN > 0  && <span style={{ fontSize: 10, color: '#ed8936' }}>! {counts.WARN}</span>}
          {counts.FAIL > 0  && <span style={{ fontSize: 10, color: '#f56565' }}>✗ {counts.FAIL}</span>}
          {counts.MANUAL > 0 && <span style={{ fontSize: 10, color: '#718096' }}>? {counts.MANUAL}</span>}
        </div>
      </div>
      {rules.map(r => <RuleRow key={r.rule_id} rule={r} />)}
    </div>
  )
}

export default function RuleResults({ ruleResults }) {
  if (!ruleResults?.length) return null

  const phases = {}
  ruleResults.forEach(r => {
    if (!phases[r.phase_id]) phases[r.phase_id] = { name: r.phase_name, rules: [] }
    phases[r.phase_id].rules.push(r)
  })

  const totalQuant = ruleResults.filter(r => r.rule_type === 'quantitative')
  const passes = totalQuant.filter(r => r.status === 'PASS').length
  const warns  = totalQuant.filter(r => r.status === 'WARN').length
  const fails  = totalQuant.filter(r => r.status === 'FAIL').length

  return (
    <div style={{
      background: '#161b27',
      border: '1px solid #2d3748',
      borderRadius: 12,
      padding: '20px 24px',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#718096' }}>
          Rule Analysis — Buffett / Graham / Lynch
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 12, fontSize: 12 }}>
          <span style={{ color: '#48bb78' }}>✓ {passes} Pass</span>
          <span style={{ color: '#ed8936' }}>! {warns} Warn</span>
          <span style={{ color: '#f56565' }}>✗ {fails} Fail</span>
          <span style={{ color: '#718096' }}>? {ruleResults.length - totalQuant.length} Manual</span>
        </div>
      </div>
      <div style={{ fontSize: 11, color: '#4a5568', marginBottom: 16 }}>
        Click any rule to expand details. Qualitative rules (marked ?) require your own judgment.
      </div>

      {Object.entries(phases).map(([id, { name, rules }]) => (
        <PhaseSection key={id} phaseId={id} phaseName={name} rules={rules} />
      ))}
    </div>
  )
}
