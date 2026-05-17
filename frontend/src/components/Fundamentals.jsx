function fmt(val, prefix = '', suffix = '', decimals = 2) {
  if (val == null) return 'N/A'
  if (Math.abs(val) >= 1e12) return `${prefix}${(val / 1e12).toFixed(decimals)}T${suffix}`
  if (Math.abs(val) >= 1e9)  return `${prefix}${(val / 1e9).toFixed(decimals)}B${suffix}`
  if (Math.abs(val) >= 1e6)  return `${prefix}${(val / 1e6).toFixed(decimals)}M${suffix}`
  return `${prefix}${Number(val).toFixed(decimals)}${suffix}`
}

function pctFmt(val) {
  if (val == null) return 'N/A'
  const pct = (val * 100).toFixed(1)
  return `${val >= 0 ? '' : ''}${pct}%`
}

function pctColor(val) {
  if (val == null) return '#e2e8f0'
  return val >= 0 ? '#48bb78' : '#f56565'
}

const Row = ({ label, value, valueStyle }) => (
  <tr>
    <td style={{ padding: '9px 0', color: '#718096', borderBottom: '1px solid #1e2535' }}>{label}</td>
    <td style={{ padding: '9px 0', textAlign: 'right', fontWeight: 600, borderBottom: '1px solid #1e2535', ...valueStyle }}>
      {value}
    </td>
  </tr>
)

export default function Fundamentals({ fundamentals: f }) {
  if (!f) return null

  return (
    <div style={{
      background: '#161b27',
      border: '1px solid #2d3748',
      borderRadius: 12,
      padding: '20px 24px',
    }}>
      <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#718096', marginBottom: 16 }}>
        Fundamentals
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <tbody>
          <Row label="EPS (TTM)" value={f.eps_ttm != null ? `$${f.eps_ttm.toFixed(2)}` : 'N/A'} />
          <Row label="Revenue (TTM)" value={fmt(f.revenue_ttm, '$')} />
          <Row
            label="Revenue Growth (YoY)"
            value={pctFmt(f.revenue_growth_yoy)}
            valueStyle={{ color: pctColor(f.revenue_growth_yoy) }}
          />
          <Row
            label="Earnings Growth"
            value={pctFmt(f.earnings_growth)}
            valueStyle={{ color: pctColor(f.earnings_growth) }}
          />
          <Row label="Gross Margin" value={pctFmt(f.gross_margin)} />
          <Row label="Operating Margin" value={pctFmt(f.operating_margin)} />
          <Row label="Net Margin" value={pctFmt(f.net_margin)} />
          <Row label="Free Cash Flow" value={fmt(f.free_cash_flow, '$')} />
          <Row label="Return on Equity" value={pctFmt(f.roe)} valueStyle={{ color: f.roe >= 0.15 ? '#48bb78' : f.roe >= 0.10 ? '#ed8936' : '#f56565' }} />
          <Row label="Return on Assets" value={pctFmt(f.roa)} />
          <Row label="Debt / Equity" value={f.debt_to_equity != null ? f.debt_to_equity.toFixed(2) : 'N/A'} />
          <Row label="Book Value / Share" value={f.book_value != null ? `$${f.book_value.toFixed(2)}` : 'N/A'} />
          <Row label="Dividend Yield" value={f.dividend_yield != null ? pctFmt(f.dividend_yield) : 'None'} />
        </tbody>
      </table>
    </div>
  )
}
