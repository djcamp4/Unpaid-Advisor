import { useState } from 'react'
import { analyzeStock } from './api'
import Verdict from './components/Verdict'
import KpiTiles from './components/KpiTiles'
import PriceChart from './components/PriceChart'
import Fundamentals from './components/Fundamentals'
import Technical from './components/Technical'
import News from './components/News'
import Debate from './components/Debate'

const styles = {
  nav: {
    background: '#161b27',
    borderBottom: '1px solid #2d3748',
    padding: '0 32px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    height: 60,
    position: 'sticky',
    top: 0,
    zIndex: 100,
  },
  brand: { fontSize: 18, fontWeight: 700, color: '#63b3ed', letterSpacing: '-0.5px' },
  brandSpan: { color: '#e2e8f0' },
  searchRow: { display: 'flex', gap: 8 },
  input: {
    background: '#1e2535',
    border: '1px solid #2d3748',
    borderRadius: 8,
    color: '#e2e8f0',
    fontSize: 14,
    padding: '8px 14px',
    width: 220,
    outline: 'none',
    textTransform: 'uppercase',
  },
  btn: {
    background: '#3182ce',
    border: 'none',
    borderRadius: 8,
    color: '#fff',
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: 600,
    padding: '8px 20px',
  },
  main: { maxWidth: 1280, margin: '0 auto', padding: '28px 24px', display: 'grid', gap: 20 },
  tickerHeader: { display: 'flex', alignItems: 'baseline', gap: 14, flexWrap: 'wrap' },
  symbol: { fontSize: 30, fontWeight: 800 },
  companyName: { fontSize: 14, color: '#718096' },
  price: { fontSize: 30, fontWeight: 700, marginLeft: 'auto' },
  changeBadge: (pos) => ({
    fontSize: 13,
    fontWeight: 600,
    padding: '3px 10px',
    borderRadius: 6,
    background: pos ? 'rgba(72,187,120,0.15)' : 'rgba(245,101,101,0.15)',
    color: pos ? '#48bb78' : '#f56565',
  }),
  grid2eq: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 },
  emptyState: {
    textAlign: 'center',
    padding: '80px 24px',
    color: '#4a5568',
  },
  emptyTitle: { fontSize: 22, fontWeight: 700, color: '#718096', marginBottom: 10 },
  emptyHint: { fontSize: 14 },
  errorBox: {
    background: 'rgba(245,101,101,0.1)',
    border: '1px solid rgba(245,101,101,0.3)',
    borderRadius: 10,
    padding: '16px 20px',
    color: '#f56565',
    fontSize: 14,
  },
  spinner: {
    textAlign: 'center',
    padding: '80px 24px',
    color: '#63b3ed',
    fontSize: 15,
  },
}

export default function App() {
  const [ticker, setTicker] = useState('')
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  async function handleAnalyze(e) {
    e.preventDefault()
    const sym = ticker.trim().toUpperCase()
    if (!sym) return
    setLoading(true)
    setError(null)
    setData(null)
    try {
      const result = await analyzeStock(sym)
      setData(result)
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Unknown error'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  const pos = data && data.change >= 0

  return (
    <>
      <nav style={styles.nav}>
        <div style={styles.brand}>Unpaid<span style={styles.brandSpan}>Advisor</span></div>
        <form style={styles.searchRow} onSubmit={handleAnalyze}>
          <input
            style={styles.input}
            placeholder="Ticker (e.g. AAPL)"
            value={ticker}
            onChange={e => setTicker(e.target.value)}
            disabled={loading}
          />
          <button style={styles.btn} type="submit" disabled={loading}>
            {loading ? 'Analyzing…' : 'Analyze'}
          </button>
        </form>
      </nav>

      <main style={styles.main}>
        {error && <div style={styles.errorBox}>Error: {error}</div>}

        {loading && (
          <div style={styles.spinner}>
            Processing…
          </div>
        )}

        {!loading && !data && !error && (
          <div style={styles.emptyState}>
            <div style={styles.emptyTitle}>Enter a ticker symbol to begin</div>
            <div style={styles.emptyHint}>
              Analysis applies 20 rules from Warren Buffett, Benjamin Graham, and Peter Lynch
            </div>
          </div>
        )}

        {data && (
          <>
            {/* Header */}
            <div style={styles.tickerHeader}>
              <div style={styles.symbol}>{data.symbol}</div>
              <div style={styles.companyName}>
                {data.company_name} · {data.exchange}
                {data.sector ? ` · ${data.sector}` : ''}
              </div>
              <div style={styles.price}>${data.price?.toFixed(2) ?? '—'}</div>
              {data.change != null && (
                <div style={styles.changeBadge(pos)}>
                  {pos ? '+' : ''}{data.change.toFixed(2)} ({pos ? '+' : ''}{data.change_pct?.toFixed(2)}%)
                </div>
              )}
            </div>

            {/* Rule-based verdict bar */}
            <Verdict
              verdict={data.verdict}
              confidence={data.confidence}
              factors={data.factors}
            />

            {/* AI Debate */}
            <Debate debate={data.debate} />

            {/* KPIs */}
            <KpiTiles kpis={data.kpis} price={data.price} />

            {/* Price Chart (full width) */}
            <PriceChart history={data.history} />

            {/* Fundamentals + Technical */}
            <div style={styles.grid2eq}>
              <Fundamentals fundamentals={data.fundamentals} />
              <Technical technicals={data.technicals} />
            </div>

            {/* News */}
            <News news={data.news} />
          </>
        )}
      </main>
    </>
  )
}
