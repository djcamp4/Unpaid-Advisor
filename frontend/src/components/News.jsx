const SENT_STYLE = {
  positive: { bg: 'rgba(72,187,120,0.12)',  color: '#48bb78' },
  negative: { bg: 'rgba(245,101,101,0.12)', color: '#f56565' },
  neutral:  { bg: 'rgba(160,174,192,0.10)', color: '#a0aec0' },
}

export default function News({ news }) {
  if (!news?.length) return null

  return (
    <div style={{
      background: '#161b27',
      border: '1px solid #2d3748',
      borderRadius: 12,
      padding: '20px 24px',
    }}>
      <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#718096', marginBottom: 16 }}>
        Recent News &amp; Sentiment
      </div>

      {news.map((item, i) => {
        const s = SENT_STYLE[item.sentiment] || SENT_STYLE.neutral
        return (
          <div key={i} style={{
            padding: '11px 0',
            borderBottom: i < news.length - 1 ? '1px solid #1e2535' : 'none',
          }}>
            <a
              href={item.url || '#'}
              target="_blank"
              rel="noopener noreferrer"
              style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0', display: 'block', marginBottom: 5 }}
            >
              {item.title}
            </a>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center', fontSize: 11, color: '#718096' }}>
              {item.publisher && <span>{item.publisher}</span>}
              {item.published_at && <span>{item.published_at}</span>}
              <span style={{
                padding: '1px 7px',
                borderRadius: 4,
                fontWeight: 700,
                fontSize: 10,
                textTransform: 'uppercase',
                background: s.bg,
                color: s.color,
              }}>
                {item.sentiment}
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}
