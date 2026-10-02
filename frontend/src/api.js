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
  const close = () => { closed = true; source.close() }

  source.onmessage = (e) => {
    if (closed) return
    let event
    try {
      event = JSON.parse(e.data)
    } catch { return }
    if (event.type === 'complete' || event.type === 'error') close()
    onEvent(event)
  }

  source.onerror = () => {
    if (closed) return
    close()
    onEvent({ type: 'error', message: 'The connection ended before analysis finished. Please retry the scan.' })
  }

  return close
}
