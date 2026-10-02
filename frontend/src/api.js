import axios from 'axios'

const BASE = import.meta.env.VITE_API_URL || ''

export async function analyzeStock(symbol, signal) {
  const { data } = await axios.get(`${BASE}/analyze/${encodeURIComponent(symbol.toUpperCase())}`, { signal })
  return data
}

/**
 * Opens an SSE connection to /stock-selector and calls `onEvent` for each
 * parsed event object. Returns a cleanup function to close the connection.
 */
export function startStockSelector(onEvent) {
  const url = `${BASE}/stock-selector`
  const source = new EventSource(url)
  let closed = false
  let lastStatus = 'Starting congressional analysis'
  const startedAt = Date.now()
  const close = () => { closed = true; source.close() }

  source.onmessage = (e) => {
    if (closed) return
    let event
    try {
      event = JSON.parse(e.data)
    } catch { return }
    if (event.type === 'status') lastStatus = event.message
    if (event.type === 'complete' || event.type === 'error') close()
    onEvent(event)
  }

  source.onerror = () => {
    if (closed) return
    close()
    const seconds = Math.round((Date.now() - startedAt) / 1000)
    const reason = typeof navigator !== 'undefined' && navigator.onLine === false
      ? 'Your browser is offline. Reconnect to the internet and retry.'
      : 'The live connection closed without a server error report. The cause could be a network interruption, timeout, or server restart. Please retry.'
    onEvent({ type: 'error', message: `Connection lost after ${seconds} seconds. Last stage: ${lastStatus} ${reason}` })
  }

  return close
}
