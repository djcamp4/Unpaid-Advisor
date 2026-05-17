function fmt(val, prefix = '') {
  if (val == null) return 'N/A'
  if (Math.abs(val) >= 1e12) return `${prefix}${(val / 1e12).toFixed(2)}T`
  if (Math.abs(val) >= 1e9)  return `${prefix}${(val / 1e9).toFixed(2)}B`
  if (Math.abs(val) >= 1e6)  return `${prefix}${(val / 1e6).toFixed(2)}M`
  return `${prefix}${val.toLocaleString()}`
}

function pct52(price, low, high) {
  if (!price || !low || !high || high === low) return null
  return Math.round(((price - low) / (high - low)) * 100)
}

export default function KpiTiles({ kpis, price }) {
  if (!kpis) return null
  const p52 = pct52(price, kpis.week_52_low, kpis.week_52_high)

  const tiles = [
    {
      label: 'Market Cap',
      value: fmt(kpis.market_cap, '$'),
      sub: kpis.market_cap >= 200e9 ? 'Mega cap' : kpis.market_cap >= 10e9 ? 'Large cap' : 'Mid/Small cap',
    },
    {
      label: 'P/E Ratio',
      value: kpis.pe_ratio != null ? `${kpis.pe_ratio.toFixed(1)}×` : 'N/A',
      sub: kpis.forward_pe != null ? `Fwd: ${kpis.forward_pe.toFixed(1)}×` : '',
    },
    {
      label: '52-Week Range',
      value: (kpis.week_52_low != null && kpis.week_52_high != null)
        ? `$${kpis.week_52_low.toFixed(0)} – $${kpis.week_52_high.toFixed(0)}`
        : 'N/A',
      sub: p52 != null ? `At ${p52}th percentile` : '',
      smallValue: true,
    },
    {
      label: 'Avg Volume',
      value: fmt(kpis.avg_volume),
      sub: kpis.volume != null ? `Today: ${fmt(kpis.volume)}` : '',
    },
    {
      label: 'PEG Ratio',
      value: kpis.peg_ratio != null ? kpis.peg_ratio.toFixed(2) : 'N/A',
      sub: kpis.peg_ratio != null ? (kpis.peg_ratio <= 1 ? 'Cheap' : kpis.peg_ratio <= 1.5 ? 'Fair' : 'Expensive') : '',
    },
    {
      label: 'P/Book',
      value: kpis.price_to_book != null ? `${kpis.price_to_book.toFixed(2)}×` : 'N/A',
      sub: '',
    },
    {
      label: 'EPS (TTM)',
      value: kpis.eps_ttm != null ? `$${kpis.eps_ttm.toFixed(2)}` : 'N/A',
      sub: kpis.forward_eps != null ? `Fwd: $${kpis.forward_eps.toFixed(2)}` : '',
    },
    {
      label: 'Dividend Yield',
      value: kpis.dividend_yield != null ? `${(kpis.dividend_yield * 100).toFixed(2)}%` : 'None',
      sub: kpis.beta != null ? `Beta: ${kpis.beta.toFixed(2)}` : '',
    },
  ]

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(4, 1fr)',
      gap: 12,
    }}>
      {tiles.map(t => (
        <div key={t.label} style={{
          background: '#1a2035',
          border: '1px solid #2d3748',
          borderRadius: 10,
          padding: 16,
        }}>
          <div style={{ fontSize: 11, color: '#718096', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
            {t.label}
          </div>
          <div style={{ fontSize: t.smallValue ? 16 : 20, fontWeight: 700, lineHeight: 1.2 }}>
            {t.value}
          </div>
          {t.sub && (
            <div style={{ fontSize: 11, color: '#718096', marginTop: 4 }}>{t.sub}</div>
          )}
        </div>
      ))}
    </div>
  )
}
