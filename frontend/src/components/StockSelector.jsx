import { useState, useRef, useEffect } from 'react'
import { startStockSelector } from '../api'

const s = {
  section: {
    background: '#161b27',
    border: '1px solid #2d3748',
    borderRadius: 14,
    padding: '24px 28px',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 20,
    flexWrap: 'wrap',
    gap: 12,
  },
  titleGroup: { display: 'flex', flexDirection: 'column', gap: 4 },
  title: { fontSize: 18, fontWeight: 700, color: '#e2e8f0', letterSpacing: '-0.3px' },
  subtitle: { fontSize: 12, color: '#4a5568' },
  btn: {
    background: '#3182ce',
    border: 'none',
    borderRadius: 8,
    color: '#fff',
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: 600,
    padding: '9px 22px',
    transition: 'opacity 0.2s',
  },
  btnDisabled: { opacity: 0.5, cursor: 'not-allowed' },
  // Progress
  progressWrap: { marginTop: 4 },
  statusLine: { fontSize: 13, color: '#63b3ed', marginBottom: 14 },
  progressBar: { height: 4, background: '#1e2535', borderRadius: 2, overflow: 'hidden', marginBottom: 16 },
  progressFill: (pct) => ({
    height: '100%',
    borderRadius: 2,
    width: `${pct}%`,
    background: 'linear-gradient(90deg, #3182ce, #63b3ed)',
    transition: 'width 0.8s ease',
  }),
  tickerLog: { display: 'flex', flexWrap: 'wrap', gap: 6 },
  tickerChip: (active) => ({
    fontSize: 11,
    fontWeight: 600,
    padding: '3px 9px',
    borderRadius: 20,
    background: active ? 'rgba(49,130,206,0.2)' : '#1e2535',
    color: active ? '#63b3ed' : '#4a5568',
    border: `1px solid ${active ? '#3182ce' : '#2d3748'}`,
    transition: 'all 0.3s',
  }),
  // Results
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
    gap: 14,
    marginTop: 4,
  },
  card: {
    background: '#1a2035',
    border: '1px solid #2d3748',
    borderRadius: 10,
    padding: '16px 14px',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 8,
    textAlign: 'center',
  },
  logoBox: {
    width: 44,
    height: 44,
    borderRadius: 10,
    overflow: 'hidden',
    background: '#2d3748',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  logoImg: { width: '100%', height: '100%', objectFit: 'contain' },
  logoFallback: { fontSize: 18, fontWeight: 800, color: '#63b3ed' },
  cardSymbol: { fontSize: 17, fontWeight: 800, color: '#e2e8f0' },
  cardName: { fontSize: 11, color: '#718096', lineHeight: 1.3 },
  buyBadge: {
    fontSize: 11,
    fontWeight: 700,
    padding: '2px 10px',
    borderRadius: 20,
    background: 'rgba(72,187,120,0.15)',
    color: '#48bb78',
    border: '1px solid rgba(72,187,120,0.3)',
  },
  confidence: { fontSize: 12, color: '#718096' },
  errorBox: {
    background: 'rgba(245,101,101,0.1)',
    border: '1px solid rgba(245,101,101,0.3)',
    borderRadius: 8,
    padding: '12px 16px',
    color: '#f56565',
    fontSize: 13,
  },
  noResults: { fontSize: 13, color: '#718096', textAlign: 'center', padding: '16px 0' },
}

function LogoIcon({ iconUrl, symbol }) {
  const [failed, setFailed] = useState(false)
  const fallbackUrl = `https://assets.parqet.com/logos/symbol/${symbol}?format=svg`
  const src = !failed && iconUrl ? iconUrl : (!failed ? fallbackUrl : null)

  return (
    <div style={s.logoBox}>
      {src ? (
        <img
          src={src}
          alt={symbol}
          style={s.logoImg}
          onError={() => setFailed(true)}
        />
      ) : (
        <span style={s.logoFallback}>{symbol[0]}</span>
      )}
    </div>
  )
}

const STORAGE_KEY = 'stockSelector_lastRun'

function loadSaved() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch { return null }
}

export default function StockSelector() {
  const saved = loadSaved()
  const [phase, setPhase] = useState(saved ? 'done' : 'idle')
  const [statusMsg, setStatusMsg] = useState('')
  const [checked, setChecked] = useState([])
  const [activeTicker, setActiveTicker] = useState(null)
  const [found, setFound] = useState(0)
  const [stocks, setStocks] = useState(saved?.stocks ?? [])
  const [lastRanAt, setLastRanAt] = useState(saved?.ranAt ?? null)
  const [errorMsg, setErrorMsg] = useState('')
  const cleanupRef = useRef(null)

  // Close connection on unmount
  useEffect(() => () => { if (cleanupRef.current) cleanupRef.current() }, [])

  const progressPct = phase === 'done' ? 100 : Math.min(95, (found / 5) * 90 + (checked.length > 0 ? 5 : 0))

  function handleStart() {
    if (phase === 'running') return
    // Close any existing connection before starting fresh
    if (cleanupRef.current) { cleanupRef.current(); cleanupRef.current = null }
    setPhase('running')
    setStatusMsg('Connecting…')
    setChecked([])
    setActiveTicker(null)
    setFound(0)
    setStocks([])
    setErrorMsg('')

    const cleanup = startStockSelector((event) => {
      switch (event.type) {
        case 'status':
          setStatusMsg(event.message)
          break
        case 'analyzing':
          setActiveTicker(event.ticker)
          setChecked(prev => prev.includes(event.ticker) ? prev : [...prev, event.ticker])
          setStatusMsg(`Analyzing ${event.ticker}…`)
          break
        case 'found':
          setStocks(prev => {
            if (prev.length >= 5) return prev
            return [...prev, event.stock]
          })
          setFound(f => {
            const next = f + 1
            if (next >= 5) {
              setTimeout(() => {
                if (cleanupRef.current) { cleanupRef.current(); cleanupRef.current = null }
                setPhase('done')
                setStatusMsg('')
              }, 0)
            }
            return next
          })
          setActiveTicker(null)
          break
        case 'complete': {
          const ranAt = new Date().toLocaleString()
          setLastRanAt(ranAt)
          setStocks(prev => {
            try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ stocks: prev, ranAt })) } catch {}
            return prev
          })
          setPhase('done')
          setStatusMsg('')
          setActiveTicker(null)
          if (cleanupRef.current) { cleanupRef.current(); cleanupRef.current = null }
          break
        }
        case 'error':
          setPhase('error')
          setErrorMsg(event.message)
          if (cleanupRef.current) { cleanupRef.current(); cleanupRef.current = null }
          break
      }
    })
    cleanupRef.current = cleanup
  }

  const isRunning = phase === 'running'

  return (
    <div style={s.section}>
      <div style={s.header}>
        <div style={s.titleGroup}>
          <div style={s.title}>Stock Selector</div>
          <div style={s.subtitle}>
            Ethically sourced stock picks from unethical people
          </div>
          {lastRanAt && !isRunning && (
            <div style={{ fontSize: 11, color: '#4a5568', marginTop: 2 }}>Last ran {lastRanAt}</div>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {lastRanAt && (
            <button
              style={{ ...s.btn, background: '#2d3748' }}
              onClick={() => { const s = loadSaved(); if (s) { setStocks(s.stocks); setLastRanAt(s.ranAt); setPhase('done') } }}
              disabled={isRunning}
            >
              Current Picks
            </button>
          )}
          {isRunning ? (
            <button
              style={{ ...s.btn, background: '#c53030' }}
              onClick={() => {
                if (cleanupRef.current) { cleanupRef.current(); cleanupRef.current = null }
                setPhase('done')
                setStatusMsg('')
                setActiveTicker(null)
              }}
            >
              Cancel
            </button>
          ) : (
            <button style={s.btn} onClick={handleStart}>
              Find Congressional Picks
            </button>
          )}
        </div>
      </div>

      {phase === 'error' && (
        <div style={s.errorBox}>{errorMsg}</div>
      )}

      {phase === 'running' && (
        <div style={s.progressWrap}>
          <div style={s.statusLine}>{statusMsg} &nbsp;·&nbsp; {found}/5 found</div>
          <div style={s.progressBar}>
            <div style={s.progressFill(progressPct)} />
          </div>
          <div style={s.tickerLog}>
            {checked.map(t => (
              <span key={t} style={s.tickerChip(t === activeTicker)}>{t}</span>
            ))}
          </div>
        </div>
      )}

      {(phase === 'done' || (phase === 'running' && stocks.length > 0)) && stocks.length > 0 && (
        <div style={{ ...s.grid, marginTop: phase === 'running' ? 20 : 4 }}>
          {stocks.map(stock => (
            <div key={stock.symbol} style={s.card}>
              <LogoIcon iconUrl={stock.icon_url} symbol={stock.symbol} />
              <div style={s.cardSymbol}>{stock.symbol}</div>
              <div style={s.cardName}>{stock.company_name}</div>
              <div style={s.buyBadge}>BUY</div>
              {stock.confidence != null && (
                <div style={s.confidence}>{stock.confidence}% confidence</div>
              )}
            </div>
          ))}
        </div>
      )}

      {phase === 'done' && stocks.length === 0 && (
        <div style={s.noResults}>
          No stocks received a BUY verdict from the Judge in this scan.
        </div>
      )}
    </div>
  )
}
