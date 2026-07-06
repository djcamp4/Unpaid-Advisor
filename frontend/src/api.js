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
  let foundCount = 0

  source.onmessage = (e) => {
    try {
      const event = JSON.parse(e.data)
      if (event.type === 'found') foundCount++
      onEvent(event)
    } catch { /* ignore parse errors */ }
  }

  source.onerror = () => {
    source.close()
    if (foundCount > 0) {
      // Preserve stocks already found rather than replacing them with a hard error
      onEvent({ type: 'complete' })
    } else {
      onEvent({ type: 'error', message: 'Connection lost. Please try again.' })
    }
  }

  return () => source.close()
}
