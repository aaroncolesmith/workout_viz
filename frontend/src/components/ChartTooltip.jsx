/** The one tooltip box shared by every chart. */
export default function ChartTooltip({ title, rows = [], children }) {
  return (
    <div style={{
      background: '#0d0d0f',
      border: '1px solid #2a2a32',
      borderRadius: 8,
      padding: '8px 12px',
      fontSize: 12,
      lineHeight: 1.5,
      maxWidth: 260,
      pointerEvents: 'none',
    }}>
      {title && <div style={{ fontWeight: 600, marginBottom: 4, color: 'var(--text-primary)' }}>{title}</div>}
      {rows.filter(Boolean).map((r, i) => (
        <div key={i} style={{ color: r.color || 'var(--text-secondary)', fontFamily: r.mono ? 'var(--font-display)' : undefined }}>
          {r.text}
        </div>
      ))}
      {children}
    </div>
  );
}
