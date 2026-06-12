import { useState, useEffect } from 'react'
import { analyzeStock } from './api'
import Verdict from './components/Verdict'
import KpiTiles from './components/KpiTiles'
import PriceChart from './components/PriceChart'
import Fundamentals from './components/Fundamentals'
import Technical from './components/Technical'
import News from './components/News'
import Debate from './components/Debate'
import StockSelector from './components/StockSelector'

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

const LOADING_STEPS = [
  { delay: 0,     pct: 5,  label: 'Fetching market data',                 detail: 'Pulling price, financials, and news from Polygon…' },
  { delay: 5000,  pct: 20, label: 'Running investment rules',             detail: 'Applying Buffett / Graham / Lynch criteria…' },
  { delay: 11000, pct: 38, label: 'Value investor is analyzing',          detail: 'Reviewing fundamentals, valuation, and margin of safety…' },
  { delay: 32000, pct: 60, label: 'Growth investor is making their case', detail: 'Evaluating momentum, TAM, and future earnings power…' },
  { delay: 53000, pct: 82, label: 'Judge Agent is weighing both arguments', detail: 'Reviewing the debate and forming a final verdict…' },
]

export default function App() {
  const [ticker, setTicker] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadingStep, setLoadingStep] = useState(0)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!loading) { setLoadingStep(0); return }
    const timers = LOADING_STEPS.map((s, i) => setTimeout(() => setLoadingStep(i), s.delay))
    return () => timers.forEach(clearTimeout)
  }, [loading])

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
      </nav>

      <main style={styles.main}>
        <StockSelector onSelect={sym => {
          setTicker(sym)
          setData(null)
          setError(null)
          setLoading(true)
          analyzeStock(sym)
            .then(result => setData(result))
            .catch(err => setError(err.response?.data?.detail || err.message || 'Unknown error'))
            .finally(() => setLoading(false))
          window.scrollTo({ top: document.getElementById('stock-analysis')?.offsetTop - 20, behavior: 'smooth' })
        }} />

        {/* Stock Analysis panel */}
        <div id="stock-analysis" style={{
          background: '#161b27',
          border: '1px solid #2d3748',
          borderRadius: 14,
          padding: '24px 28px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <div style={{ fontSize: 18, fontWeight: 700, color: '#e2e8f0', letterSpacing: '-0.3px' }}>Stock Analysis</div>
              <div style={{ fontSize: 12, color: '#4a5568' }}>Enter a ticker to run a full value &amp; growth analysis</div>
            </div>
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
          </div>

          {error && <div style={styles.errorBox}>Error: {error}</div>}

          {loading && (
            <div style={{ padding: '40px 24px', maxWidth: 520, margin: '0 auto' }}>
              <div style={{ marginBottom: 36 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                  <span style={{ fontSize: 12, color: '#718096' }}>{LOADING_STEPS[loadingStep]?.label}…</span>
                  <span style={{ fontSize: 12, fontWeight: 700, color: '#63b3ed' }}>{LOADING_STEPS[loadingStep]?.pct}%</span>
                </div>
                <div style={{ height: 6, background: '#1e2535', borderRadius: 3, overflow: 'hidden' }}>
                  <div style={{
                    height: '100%', borderRadius: 3,
                    width: `${LOADING_STEPS[loadingStep]?.pct ?? 5}%`,
                    background: 'linear-gradient(90deg, #3182ce, #63b3ed)',
                    transition: 'width 1.2s ease',
                  }} />
                </div>
              </div>
              {LOADING_STEPS.map((s, i) => {
                const done = i < loadingStep
                const active = i === loadingStep
                return (
                  <div key={i} style={{ display: 'flex', gap: 16, marginBottom: 20, opacity: done ? 0.4 : active ? 1 : 0.2 }}>
                    <div style={{
                      flexShrink: 0, width: 22, height: 22, borderRadius: '50%', marginTop: 2,
                      background: done ? '#48bb78' : active ? '#3182ce' : '#2d3748',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 11, fontWeight: 700, color: '#fff',
                      boxShadow: active ? '0 0 0 4px rgba(49,130,206,0.25)' : 'none',
                      transition: 'background 0.4s ease',
                    }}>
                      {done ? '✓' : i + 1}
                    </div>
                    <div>
                      <div style={{ fontSize: 14, fontWeight: active ? 700 : 500, color: active ? '#e2e8f0' : '#718096' }}>
                        {s.label}{active ? '…' : ''}
                      </div>
                      {active && <div style={{ fontSize: 12, color: '#4a5568', marginTop: 3 }}>{s.detail}</div>}
                    </div>
                  </div>
                )
              })}
            </div>
          )}

        </div>

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
