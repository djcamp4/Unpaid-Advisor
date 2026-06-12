import axios from 'axios'

const BASE = import.meta.env.VITE_API_URL || ''

export async function analyzeStock(symbol) {
  const { data } = await axios.get(`${BASE}/analyze/${encodeURIComponent(symbol.toUpperCase())}`)
  return data
}

/**
 * Opens an SSE connection to /stock-selector and calls `onEvent` for each
 * parsed event object. Returns a cleanup function to close the connection.
 */
export function startStockSelector(onEvent) {
  const url = `${BASE}/stock-selector`
  const source = new EventSource(url)

  source.onmessage = (e) => {
    try {
      onEvent(JSON.parse(e.data))
    } catch { /* ignore parse errors */ }
  }

  source.onerror = () => {
    onEvent({ type: 'error', message: 'Connection lost. Please try again.' })
    source.close()
  }

  return () => source.close()
}
