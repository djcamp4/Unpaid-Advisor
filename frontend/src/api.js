import axios from 'axios'

const BASE = import.meta.env.VITE_API_URL || ''

export async function analyzeStock(symbol) {
  const { data } = await axios.get(`${BASE}/analyze/${encodeURIComponent(symbol.toUpperCase())}`)
  return data
}
